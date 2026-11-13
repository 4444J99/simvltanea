import Foundation
import SimvltaneaKit

// simv-library: build, check and serve a private clip library without the app or Photos.
//   simv-library import-folder <videos> <library-root>
//   simv-library verify <library-root>
//   simv-library serve <studio-dir> <library-root>
let usage = """
usage: simv-library import-folder <videos> <library-root>
       simv-library verify <library-root>
       simv-library serve <studio-dir> <library-root>
"""

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

func run() async {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard let command = arguments.first else { fail(usage) }
    switch (command, arguments.count) {
    case ("import-folder", 3):
        let store = LibraryStore(root: URL(fileURLWithPath: arguments[2]))
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent("simv-library-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: scratch) }
        do {
            let result = try await store.importFolder(URL(fileURLWithPath: arguments[1])) { source in
                try await ClipTranscoder.prepare(source, scratch: scratch)
            }
            print("imported \(result.added.count) clips, skipped \(result.skipped.count)")
            for line in result.skipped { FileHandle.standardError.write(Data((line + "\n").utf8)) }
            exit(result.added.isEmpty && !result.skipped.isEmpty ? 1 : 0)
        } catch { fail("refused: \(error)") }
    case ("verify", 2):
        do {
            let manifest = try LibraryStore(root: URL(fileURLWithPath: arguments[1])).verify()
            print("library ok: \(manifest.clips.count) clips")
            exit(0)
        } catch { fail("refused: \(error)") }
    case ("serve", 3):
        let store = LibraryStore(root: URL(fileURLWithPath: arguments[2]))
        let server = LocalSiteServer(mounts: [
            .init(prefix: "library", directory: store.libraryDirectory),
            .init(prefix: "", directory: URL(fileURLWithPath: arguments[1])),
        ])
        do { try server.start() } catch { fail("refused: \(error)") }
        print(server.baseURL.absoluteString)
        fflush(stdout)
        while true { try? await Task.sleep(nanoseconds: 3_600_000_000_000) }
    default:
        fail(usage)
    }
}

await run()
