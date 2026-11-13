import AppKit
import SimvltaneaKit
import SwiftUI
import WebKit

/// The Mac app: the Studio in a web view, served from the app bundle and the private library,
/// with a Photos import that fills that library from the user's own videos.
@MainActor
final class AppModel: ObservableObject {
    @Published var status = "Starting"
    @Published var clipCount = 0
    @Published var importing = false
    @Published var address: URL?
    @Published var reloadCount = 0
    @Published var favoritesOnly = false

    let store: LibraryStore
    private var server: LocalSiteServer?
    private var task: Task<Void, Never>?

    init() {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Simvltanea", isDirectory: true)
        try? FileManager.default.createDirectory(at: support, withIntermediateDirectories: true)
        store = LibraryStore(root: support)
    }

    func start() {
        guard server == nil else { return }
        guard let studio = Bundle.main.resourceURL?.appendingPathComponent("studio"),
              FileManager.default.fileExists(atPath: studio.appendingPathComponent("index.html").path) else {
            status = "The Studio files are missing from the app bundle."
            return
        }
        try? FileManager.default.createDirectory(at: store.clipsDirectory, withIntermediateDirectories: true)
        let server = LocalSiteServer(mounts: [
            .init(prefix: "library", directory: store.libraryDirectory),
            .init(prefix: "", directory: studio),
        ])
        do { try server.start() } catch { status = "\(error)"; return }
        self.server = server
        address = server.baseURL
        refreshCount()
    }

    func refreshCount() {
        clipCount = (try? store.loadManifest()?.clips.count) ?? 0
        status = clipCount == 0 ? "No library yet: import from Photos to play your own clips." : "\(clipCount) clips in your library"
    }

    func importFromPhotos(criteria: PhotoCriteria) {
        guard !importing else { return }
        importing = true
        status = "Asking Photos for access"
        task = Task {
            defer { importing = false }
            guard await PhotosImporter.requestAccess() else {
                status = "Photos access is off. Allow it in System Settings, Privacy and Security, Photos."
                return
            }
            let importer = PhotosImporter(store: store)
            do {
                let result = try await importer.run(criteria: criteria) { state in
                    Task { @MainActor in
                        self.status = "Importing \(state.done) of \(state.total): \(state.added) added, \(state.skipped) skipped"
                    }
                }
                refreshCount()
                status += result.total == 0 ? " (nothing new to import)" : ""
                reloadCount += 1
            } catch is CancellationError {
                refreshCount(); status += " (import stopped)"
            } catch {
                status = "Import failed: \(error)"
            }
        }
    }

    func cancelImport() { task?.cancel() }
}

struct StudioView: NSViewRepresentable {
    let address: URL
    let generation: Int

    final class Coordinator { var generation = -1 }
    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        return WKWebView(frame: .zero, configuration: configuration)
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        guard context.coordinator.generation != generation else { return }
        context.coordinator.generation = generation
        view.load(URLRequest(url: address))
    }
}

struct ContentView: View {
    @StateObject private var model = AppModel()

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Button(model.importing ? "Stop" : "Import from Photos") {
                    if model.importing { model.cancelImport() }
                    else {
                        var criteria = PhotoCriteria()
                        criteria.favoritesOnly = model.favoritesOnly
                        model.importFromPhotos(criteria: criteria)
                    }
                }
                Toggle("Favourites only", isOn: $model.favoritesOnly).disabled(model.importing)
                Spacer()
                Text(model.status).font(.callout).foregroundStyle(.secondary).lineLimit(1)
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            Divider()
            if let address = model.address {
                StudioView(address: address, generation: model.reloadCount)
            } else {
                Spacer()
            }
        }
        .frame(minWidth: 900, minHeight: 600)
        .onAppear { model.start() }
    }
}

@main
struct SimvltaneaApp: App {
    var body: some Scene {
        WindowGroup("Simvltanea") { ContentView() }
    }
}
