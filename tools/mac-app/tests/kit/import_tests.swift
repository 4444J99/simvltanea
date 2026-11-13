import Foundation
@testable import SimvltaneaKit

final class ImportTests: XCTestCase {
    var work: URL!
    var sources: [URL] = []

    override func setUpWithError() throws {
        work = FileManager.default.temporaryDirectory.appendingPathComponent("simv-imp-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: work, withIntermediateDirectories: true)
    }

    override func tearDown() { try? FileManager.default.removeItem(at: work) }

    func makeSources(_ count: Int) async throws {
        sources = []
        for number in 0..<count {
            let url = work.appendingPathComponent("src\(number).mp4")
            try await FixtureVideo.write(to: url, width: 160, height: 120, seconds: 1 + Double(number) * 0.5, tone: number % 2 == 0 ? 330 : nil)
            sources.append(url)
        }
    }

    func candidates(_ count: Int) -> [PhotoCandidate] {
        (0..<count).map { PhotoCandidate(localIdentifier: "id\($0)", duration: 2, pixelWidth: 160, pixelHeight: 120) }
    }

    func copyOf(_ number: Int) throws -> URL {
        let copy = work.appendingPathComponent("export-\(UUID().uuidString).mp4")
        try FileManager.default.copyItem(at: sources[number], to: copy)
        return copy
    }

    func testFirstImportCreatesTheManifestAndIndexOnAFreshLibrary() async throws {
        try await makeSources(3)
        let store = LibraryStore(root: work.appendingPathComponent("fresh"))
        let state = try await ImportRunner.run(plan: candidates(3), store: store, export: { candidate in
            try self.copyOf(Int(candidate.localIdentifier.dropFirst(2))!)
        }, progress: { _ in })
        XCTAssertEqual(state, ImportProgress(done: 3, total: 3, added: 3, skipped: 0, failed: 0))
        XCTAssertEqual(try store.verify().clips.count, 3)
        XCTAssertEqual(PhotosIndex.load(from: store.photosIndexURL).imported.count, 3)
        // A second run plans nothing: everything is already indexed.
        let again = ExportPlanner.select(candidates(3), criteria: PhotoCriteria(), index: PhotosIndex.load(from: store.photosIndexURL))
        XCTAssertTrue(again.isEmpty)
    }

    func testAnExportFailureIsRetriedNextTimeButAnUnusableClipIsRemembered() async throws {
        try await makeSources(1)
        let store = LibraryStore(root: work.appendingPathComponent("root"))
        let junk = work.appendingPathComponent("junk.mp4")
        try Data("not a video".utf8).write(to: junk)
        struct Offline: Error {}
        let state = try await ImportRunner.run(plan: candidates(3), store: store, export: { candidate in
            switch candidate.localIdentifier {
            case "id0": return try self.copyOf(0)
            case "id1": throw Offline()                       // iCloud download failed
            default: let copy = self.work.appendingPathComponent("j-\(UUID().uuidString).mp4"); try FileManager.default.copyItem(at: junk, to: copy); return copy
            }
        }, progress: { _ in })
        XCTAssertEqual(state, ImportProgress(done: 3, total: 3, added: 1, skipped: 1, failed: 1))
        let index = PhotosIndex.load(from: store.photosIndexURL)
        XCTAssertNil(index.imported["id1"]); XCTAssertNil(index.skipped["id1"], "a transient failure must stay retryable")
        XCTAssertNotNil(index.skipped["id2"])
        let plan = ExportPlanner.select(candidates(3), criteria: PhotoCriteria(), index: index)
        XCTAssertEqual(plan.map(\.localIdentifier), ["id1"])
    }

    func testStoppingBetweenCheckpointsKeepsEveryFinishedClipListed() async throws {
        try await makeSources(3)
        let store = LibraryStore(root: work.appendingPathComponent("root"))
        let task = Task { () -> Error? in
            do {
                _ = try await ImportRunner.run(plan: self.candidates(3), store: store, export: { candidate in
                    let copy = try self.copyOf(Int(candidate.localIdentifier.dropFirst(2))!)
                    if candidate.localIdentifier == "id1" { withUnsafeCurrentTask { $0?.cancel() } }
                    return copy
                }, progress: { _ in })
                return nil
            } catch { return error }
        }
        let error = await task.value
        XCTAssertTrue(error is CancellationError)
        // Two clips were ingested before the cancelled loop iteration; both must be in the manifest and index.
        let manifest = try store.verify()
        XCTAssertEqual(manifest.clips.count, 2)
        XCTAssertEqual(PhotosIndex.load(from: store.photosIndexURL).imported.count, 2)
    }

    func testAtomicWriteCreatesMissingFoldersAndReplacesExistingFiles() throws {
        let target = work.appendingPathComponent("a/b/file.json")
        try AtomicFile.write(Data("one".utf8), to: target)
        try AtomicFile.write(Data("two".utf8), to: target)
        XCTAssertEqual(String(decoding: try Data(contentsOf: target), as: UTF8.self), "two")
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: target.deletingLastPathComponent().path), ["file.json"])
    }

    func testOnlyClipsInsideEveryBoundSkipTranscoding() {
        XCTAssertFalse(ClipTranscoder.needsExport(width: 1920, height: 1080, bytes: 5_000_000))
        XCTAssertTrue(ClipTranscoder.needsExport(width: 4097, height: 1080, bytes: 5_000_000))
        XCTAssertTrue(ClipTranscoder.needsExport(width: 1080, height: 7680, bytes: 5_000_000))
        XCTAssertTrue(ClipTranscoder.needsExport(width: 1920, height: 1080, bytes: LibraryLimits.maxClipBytes + 1))
        XCTAssertTrue(ClipTranscoder.needsExport(width: 1920, height: 1080, bytes: 0))
    }

    func testAudioKeepsItsPlaceOnTheClipTimeline() {
        var timeline = AudioTimeline(sampleRate: 10)
        timeline.append(interleaved: [1, 1, 1, 1], startSeconds: 0.5)          // starts 5 frames late
        XCTAssertEqual(timeline.left, [0, 0, 0, 0, 0, 1, 1])
        timeline.append(interleaved: [2, 2, 2, 2], startSeconds: 1.0)          // a 3-frame gap
        XCTAssertEqual(timeline.left, [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 2, 2])
        timeline.append(interleaved: [3, 3, 3, 3, 3, 3], startSeconds: 1.1)    // overlaps one frame
        XCTAssertEqual(Array(timeline.left.suffix(4)), [2, 2, 3, 3])
        XCTAssertEqual(timeline.left.count, timeline.right.count)
        var plain = AudioTimeline(sampleRate: 10)
        plain.append(interleaved: [1, 2, 3, 4], startSeconds: nil)
        plain.append(interleaved: [5, 6], startSeconds: nil)
        XCTAssertEqual(plain.left, [1, 3, 5]); XCTAssertEqual(plain.right, [2, 4, 6])
    }
}
