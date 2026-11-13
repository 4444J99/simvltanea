import Foundation

/// The per-video loop of a Photos import, free of PhotoKit so every branch can be tested with a
/// fake exporter. Outcomes are kept apart on purpose:
///
/// - A video the exporter could not fetch (offline iCloud, a transient Photos error) is `failed` and
///   is NOT written to the index, so the next import tries it again.
/// - A video that exported but cannot become a library clip (too large, unreadable, out of bounds)
///   is `skipped` and indexed, so it is not re-exported forever.
public enum ImportRunner {
    public static func run(plan: [PhotoCandidate], store: LibraryStore,
                           export: (PhotoCandidate) async throws -> URL,
                           progress: (ImportProgress) -> Void) async throws -> ImportProgress {
        var index = PhotosIndex.load(from: store.photosIndexURL)
        var state = ImportProgress(done: 0, total: plan.count, added: 0, skipped: 0, failed: 0)
        var pending: [ClipAsset] = []
        func flush() throws {
            if !pending.isEmpty { try store.commit(pending); pending = [] }
            try index.save(to: store.photosIndexURL)
        }
        for candidate in plan {
            do {
                try Task.checkCancellation()
                let exported: URL
                do { exported = try await export(candidate) }
                catch is CancellationError { throw CancellationError() }
                catch { state.failed += 1; state.done += 1; progress(state); continue }
                defer { try? FileManager.default.removeItem(at: exported) }
                do {
                    let facts = try await MediaProbe.facts(of: exported)
                    let asset = try store.ingest(file: exported, facts: facts)
                    pending.append(asset)
                    index.imported[candidate.localIdentifier] = asset.id
                    state.added += 1
                } catch {
                    index.skipped[candidate.localIdentifier] = String(describing: error)
                    state.skipped += 1
                }
            } catch is CancellationError {
                // Stopping keeps everything finished so far: clips on disk always have manifest entries.
                try flush()
                throw CancellationError()
            }
            state.done += 1
            if pending.count >= 8 { try flush() }
            progress(state)
        }
        try flush()
        return state
    }
}
