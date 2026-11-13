#if canImport(Photos)
import AVFoundation
import Foundation
import Photos

public struct ImportProgress {
    public var done: Int
    public var total: Int
    public var added: Int
    public var skipped: Int
}

/// Reads videos from the user's Photos library with PhotoKit and turns them into library clips.
/// Nothing is written back to Photos; originals stay where they are.
public final class PhotosImporter {
    private let store: LibraryStore
    public init(store: LibraryStore) { self.store = store }

    public static func requestAccess() async -> Bool {
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        return status == .authorized || status == .limited
    }

    public func candidates() -> [PhotoCandidate] {
        let options = PHFetchOptions()
        options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        let result = PHAsset.fetchAssets(with: .video, options: options)
        var found: [PhotoCandidate] = []
        result.enumerateObjects { asset, _, _ in
            found.append(PhotoCandidate(localIdentifier: asset.localIdentifier, duration: asset.duration,
                                        pixelWidth: asset.pixelWidth, pixelHeight: asset.pixelHeight,
                                        created: asset.creationDate, isFavorite: asset.isFavorite))
        }
        return found
    }

    /// Import the plan one clip at a time, committing the manifest every few clips so an
    /// interrupted import keeps what it finished.
    @discardableResult
    public func run(criteria: PhotoCriteria, progress: @escaping (ImportProgress) -> Void) async throws -> ImportProgress {
        var index = PhotosIndex.load(from: store.photosIndexURL)
        let plan = ExportPlanner.select(candidates(), criteria: criteria, index: index)
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent("simvltanea-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: scratch) }
        var state = ImportProgress(done: 0, total: plan.count, added: 0, skipped: 0)
        var pending: [ClipAsset] = []
        func flush() throws {
            if !pending.isEmpty { try store.commit(pending); pending = [] }
            try index.save(to: store.photosIndexURL)
        }
        for candidate in plan {
            try Task.checkCancellation()
            do {
                let exported = try await exportVideo(identifier: candidate.localIdentifier, scratch: scratch)
                let facts = try await MediaProbe.facts(of: exported)
                let asset = try store.ingest(file: exported, facts: facts)
                pending.append(asset)
                index.imported[candidate.localIdentifier] = asset.id
                state.added += 1
                try? FileManager.default.removeItem(at: exported)
            } catch is CancellationError {
                try flush()
                throw CancellationError()
            } catch {
                index.skipped[candidate.localIdentifier] = String(describing: error)
                state.skipped += 1
            }
            state.done += 1
            if pending.count >= 8 { try flush() }
            progress(state)
        }
        try flush()
        return state
    }

    func exportVideo(identifier: String, scratch: URL) async throws -> URL {
        guard let asset = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject else {
            throw LibraryError("the video is no longer in Photos")
        }
        let options = PHVideoRequestOptions()
        options.isNetworkAccessAllowed = true
        options.deliveryMode = .highQualityFormat
        options.version = .current
        let source: AVAsset = try await withCheckedThrowingContinuation { continuation in
            PHImageManager.default().requestAVAsset(forVideo: asset, options: options) { avAsset, _, info in
                if let avAsset { continuation.resume(returning: avAsset) }
                else { continuation.resume(throwing: LibraryError("Photos could not provide the video: \((info?[PHImageErrorKey] as? Error)?.localizedDescription ?? "unavailable")")) }
            }
        }
        return try await ClipTranscoder.export(asset: source, scratch: scratch)
    }
}
#endif
