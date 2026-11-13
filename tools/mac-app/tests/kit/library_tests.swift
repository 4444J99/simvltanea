import Foundation
@testable import SimvltaneaKit

final class LibraryTests: XCTestCase {
    var work: URL!

    override func setUpWithError() throws {
        work = FileManager.default.temporaryDirectory.appendingPathComponent("simv-lib-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: work, withIntermediateDirectories: true)
    }

    override func tearDown() { try? FileManager.default.removeItem(at: work) }

    func testProbeReadsSizeDurationAndRealLoudnessFromGenuineMedia() async throws {
        let url = work.appendingPathComponent("tone.mp4")
        try await FixtureVideo.write(to: url, width: 320, height: 240, seconds: 2, tone: 997)
        let facts = try await MediaProbe.facts(of: url)
        XCTAssertEqual(facts.width, 320); XCTAssertEqual(facts.height, 240)
        XCTAssertEqual(facts.duration, 2.0, accuracy: 0.1)
        XCTAssertTrue(facts.audio.hasAudio)
        XCTAssertEqual(facts.audio.rmsEnvelope.count, AudioProfile.envelopeCount(duration: facts.duration))
        // A 0.5-amplitude stereo tone is about -6 dBFS peak; AAC may overshoot a little.
        XCTAssertEqual(facts.audio.peakDbfs ?? 0, -6, accuracy: 1.5)
        XCTAssertEqual(facts.audio.lufsIntegrated ?? 0, -6.0, accuracy: 1.5)
        XCTAssertTrue(facts.audio.rmsEnvelope[10] > 0.2)
    }

    func testSilentVideoHasNoAudioAndARotatedTrackReportsItsDisplayedShape() async throws {
        let url = work.appendingPathComponent("silent.mp4")
        try await FixtureVideo.write(to: url, width: 320, height: 240, seconds: 1, tone: nil, rotate: true)
        let facts = try await MediaProbe.facts(of: url)
        XCTAssertFalse(facts.audio.hasAudio)
        XCTAssertNil(facts.audio.peakDbfs); XCTAssertNil(facts.audio.lufsIntegrated)
        XCTAssertEqual(facts.audio.rmsEnvelope, [Double](repeating: 0, count: 10))
        XCTAssertEqual(facts.width, 240); XCTAssertEqual(facts.height, 320)
    }

    func testIngestCommitAndVerifyBuildAStudioShapedLibrary() async throws {
        let source = work.appendingPathComponent("source", isDirectory: true)
        try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
        try await FixtureVideo.write(to: source.appendingPathComponent("a.mp4"), width: 320, height: 240, seconds: 1.5, tone: 440)
        try await FixtureVideo.write(to: source.appendingPathComponent("b.mp4"), width: 240, height: 320, seconds: 1, tone: nil)
        try Data("not video".utf8).write(to: source.appendingPathComponent("broken.mp4"))
        try Data("ignored".utf8).write(to: source.appendingPathComponent("notes.txt"))
        let store = LibraryStore(root: work.appendingPathComponent("root"))
        let result = try await store.importFolder(source) { $0 }
        XCTAssertEqual(result.added.count, 2)
        XCTAssertEqual(result.skipped.count, 1)
        XCTAssertTrue(result.skipped[0].hasPrefix("broken.mp4"))
        let manifest = try store.verify()
        XCTAssertEqual(manifest.clips.count, 2)
        XCTAssertEqual(Set(manifest.clips.map(\.orientation)), ["landscape", "portrait"])
        for clip in manifest.clips {
            XCTAssertEqual(try ContentID.of(fileAt: store.libraryDirectory.appendingPathComponent(clip.file)), clip.id)
        }
        // Importing the same folder again adds nothing new: content addressing makes it idempotent.
        let again = try await store.importFolder(source) { $0 }
        XCTAssertEqual(again.added.count, 2)
        XCTAssertEqual(try store.verify().clips.count, 2)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: store.clipsDirectory.path).count, 2)
    }

    func testVerifyRefusesStraysTamperingAndMissingFiles() async throws {
        let store = LibraryStore(root: work.appendingPathComponent("root"))
        let url = work.appendingPathComponent("one.mp4")
        try await FixtureVideo.write(to: url, width: 160, height: 120, seconds: 1, tone: nil)
        let asset = try store.ingest(file: url, facts: try await MediaProbe.facts(of: url))
        try store.commit([asset])
        XCTAssertNoThrow(try store.verify())
        let stray = store.clipsDirectory.appendingPathComponent("stray.mp4")
        try Data("x".utf8).write(to: stray)
        XCTAssertThrowsError(try store.verify()) { XCTAssertTrue("\($0)".contains("do not list") || "\($0)".contains("does not list")) }
        try FileManager.default.removeItem(at: stray)
        let clipFile = store.libraryDirectory.appendingPathComponent(asset.file)
        var bytes = try Data(contentsOf: clipFile); bytes[bytes.count / 2] ^= 0xff
        try bytes.write(to: clipFile)
        XCTAssertThrowsError(try store.verify()) { XCTAssertTrue("\($0)".contains("manifest id")) }
        try FileManager.default.removeItem(at: clipFile)
        XCTAssertThrowsError(try store.verify()) { XCTAssertTrue("\($0)".contains("missing")) }
    }

    func testCommitRefusesAClipThatIsNotOnDisk() throws {
        let store = LibraryStore(root: work.appendingPathComponent("root"))
        let ghost = ClipAsset(id: "deadbeef0000", width: 10, height: 10, bytes: 10, durationSeconds: 1, audio: .silent(duration: 1))
        XCTAssertThrowsError(try store.commit([ghost]))
        XCTAssertNil(try store.loadManifest())
    }

    func testOversizeFilesAreRefusedBeforeAnyCopy() throws {
        let store = LibraryStore(root: work.appendingPathComponent("root"))
        let empty = work.appendingPathComponent("empty.mp4")
        FileManager.default.createFile(atPath: empty.path, contents: Data())
        let facts = MediaFacts(width: 10, height: 10, duration: 1, audio: .silent(duration: 1))
        XCTAssertThrowsError(try store.ingest(file: empty, facts: facts))
        XCTAssertFalse(FileManager.default.fileExists(atPath: store.clipsDirectory.path))
    }
}
