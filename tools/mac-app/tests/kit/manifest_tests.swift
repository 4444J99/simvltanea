import Foundation
@testable import SimvltaneaKit

final class ManifestTests: XCTestCase {
    func profile(duration: Double) -> AudioProfile {
        AudioProfile(hasAudio: true, lufsIntegrated: -20, peakDbfs: -3,
                     rmsEnvelope: [Double](repeating: 0.1, count: AudioProfile.envelopeCount(duration: duration)))
    }

    func clip(id: String = "0123456789ab", duration: Double = 2.5, width: Int = 320, height: Int = 240) -> ClipAsset {
        ClipAsset(id: id, width: width, height: height, bytes: 1000, durationSeconds: duration, audio: profile(duration: duration))
    }

    func testContentIdentifierIsTheSha256Prefix() {
        XCTAssertEqual(ContentID.of(Data("abc".utf8)), "ba7816bf8f01")
    }

    func testValidClipRoundTripsThroughJSON() throws {
        let manifest = LibraryManifest(clips: [clip(id: "bbbbbbbbbbbb"), clip(id: "aaaaaaaaaaaa", width: 240, height: 320)])
        try manifest.validate()
        XCTAssertEqual(manifest.clips.map(\.id), ["aaaaaaaaaaaa", "bbbbbbbbbbbb"])
        XCTAssertEqual(manifest.clips[0].orientation, "portrait")
        let decoded = try JSONDecoder().decode(LibraryManifest.self, from: manifest.encoded())
        XCTAssertEqual(decoded, manifest)
        let object = try JSONSerialization.jsonObject(with: manifest.encoded()) as? [String: Any]
        XCTAssertEqual(object?["schema"] as? String, "simvltanea.public-demo/1")
    }

    func testSilentClipsWriteExplicitNulls() throws {
        let silent = ClipAsset(id: "cccccccccccc", width: 10, height: 10, bytes: 5, durationSeconds: 1, audio: .silent(duration: 1))
        try silent.validate()
        let json = String(decoding: try JSONEncoder().encode(silent), as: UTF8.self)
        XCTAssertTrue(json.contains("\"lufs_integrated\":null"))
        XCTAssertTrue(json.contains("\"peak_dbfs\":null"))
    }

    func testEveryBoundTheStudioEnforcesIsEnforcedHere() {
        func rejects(_ mutate: (inout ClipAsset) -> Void, _ fragment: String, line: UInt = #line) {
            var asset = clip(); mutate(&asset)
            XCTAssertThrowsError(try asset.validate(), line: line) { XCTAssertTrue("\($0)".contains(fragment), "\($0)", line: line) }
        }
        rejects({ $0.id = "ABCDEF012345" }, "12 lowercase hex")
        rejects({ $0.file = "clips/other.mp4" }, "clips/<id>.mp4")
        rejects({ $0.width = 4097 }, "whole pixels")
        rejects({ $0.height = 0 }, "whole pixels")
        rejects({ $0.bytes = LibraryLimits.maxClipBytes + 1 }, "bytes")
        rejects({ $0.orientation = "portrait" }, "orientation must be landscape")
        rejects({ $0.durationSeconds = 0.2 }, "duration_seconds")
        rejects({ $0.durationSeconds = 601 }, "duration_seconds")
        rejects({ $0.rmsEnvelope.removeLast() }, "rms_envelope")
        rejects({ $0.rmsEnvelope[0] = 1.5 }, "rms_envelope")
        rejects({ $0.envelopeHz = 20 }, "rms_envelope")
        rejects({ $0.peakDbfs = nil }, "peak_dbfs")
        rejects({ $0.hasAudio = false }, "peak_dbfs")
        rejects({ $0.hasAudio = false; $0.peakDbfs = nil }, "silent integrated loudness")
        rejects({ $0.lufsIntegrated = -200 }, "lufs_integrated")
    }

    func testManifestNeedsClipsAndRefusesDuplicates() {
        XCTAssertThrowsError(try LibraryManifest(clips: []).validate())
        XCTAssertThrowsError(try LibraryManifest(clips: [clip(), clip()]).validate())
        var wrong = LibraryManifest(clips: [clip()]); wrong.schema = "other/1"
        XCTAssertThrowsError(try wrong.validate())
    }

    func testEnvelopeLengthMatchesPythonCeilingForEveryWholeMillisecondDuration() {
        // Python checks len(envelope) == math.ceil(duration * 10). Durations are kept to whole
        // milliseconds, and for every such value in 0.25...600 s the double product never lands
        // just above a multiple of 0.1 s (verified exhaustively for 0.25...60 s against Python).
        for milliseconds in stride(from: 250, through: 60_000, by: 1) {
            let duration = Double(milliseconds) / 1000
            XCTAssertEqual(AudioProfile.envelopeCount(duration: duration), (milliseconds + 99) / 100, "\(milliseconds) ms")
        }
        XCTAssertEqual(AudioProfile.envelopeCount(duration: 1.1), 11)
        XCTAssertEqual(AudioProfile.envelopeCount(duration: 2.5), 25)
    }
}
