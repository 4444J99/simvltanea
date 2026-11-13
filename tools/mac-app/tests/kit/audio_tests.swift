import Foundation
@testable import SimvltaneaKit

final class AudioTests: XCTestCase {
    func sine(_ frequency: Double, amplitude: Float, seconds: Double, rate: Double = 48_000) -> [Float] {
        (0..<Int(seconds * rate)).map { amplitude * Float(sin(2 * Double.pi * frequency * Double($0) / rate)) }
    }

    func testFullScaleStereoSineIsZeroLUFSAndMonoIsThreeDecibelsLower() throws {
        let tone = sine(997, amplitude: 1, seconds: 5)
        let stereo = try XCTUnwrap(AudioAnalysis.integratedLoudness(channels: [tone, tone], sampleRate: 48_000))
        let mono = try XCTUnwrap(AudioAnalysis.integratedLoudness(channels: [tone], sampleRate: 48_000))
        XCTAssertEqual(stereo, 0.0, accuracy: 0.15)
        XCTAssertEqual(stereo - mono, 3.01, accuracy: 0.05)
    }

    func testHalvingTheAmplitudeLowersLoudnessBySixDecibels() throws {
        let loud = sine(997, amplitude: 0.8, seconds: 4), quiet = loud.map { $0 / 2 }
        let a = try XCTUnwrap(AudioAnalysis.integratedLoudness(channels: [loud, loud], sampleRate: 48_000))
        let b = try XCTUnwrap(AudioAnalysis.integratedLoudness(channels: [quiet, quiet], sampleRate: 48_000))
        XCTAssertEqual(a - b, 6.02, accuracy: 0.02)
    }

    func testGatingIgnoresSilenceAndTheKWeightingHoldsAtOtherRates() throws {
        let tone = sine(997, amplitude: 0.5, seconds: 3)
        let padded = tone + [Float](repeating: 0, count: 48_000 * 6)
        let plain = try XCTUnwrap(AudioAnalysis.integratedLoudness(channels: [tone, tone], sampleRate: 48_000))
        let gated = try XCTUnwrap(AudioAnalysis.integratedLoudness(channels: [padded, padded], sampleRate: 48_000))
        // Only the blocks straddling the tone's end differ; ungated, six silent seconds would read near -10.8.
        XCTAssertEqual(plain, gated, accuracy: 0.5)
        XCTAssertTrue(gated > -7)
        let low = sine(997, amplitude: 0.5, seconds: 3, rate: 44_100)
        let at44 = try XCTUnwrap(AudioAnalysis.integratedLoudness(channels: [low, low], sampleRate: 44_100))
        XCTAssertEqual(at44, plain, accuracy: 0.1)
    }

    func testTooShortOrSilentAudioHasNoIntegratedLoudness() {
        let short = sine(997, amplitude: 1, seconds: 0.3)
        XCTAssertNil(AudioAnalysis.integratedLoudness(channels: [short], sampleRate: 48_000))
        let silence = [Float](repeating: 0, count: 48_000)
        XCTAssertNil(AudioAnalysis.integratedLoudness(channels: [silence], sampleRate: 48_000))
    }

    func testProfileCarriesPeakAndATenHertzEnvelopeOfTheRightLength() {
        let constant = [Float](repeating: 0.5, count: 48_000 * 2)
        let profile = AudioAnalysis.profile(channels: [constant, constant], sampleRate: 48_000, duration: 2.0)
        XCTAssertTrue(profile.hasAudio)
        XCTAssertEqual(profile.peakDbfs ?? 0, -6.02, accuracy: 0.01)
        XCTAssertEqual(profile.rmsEnvelope.count, 20)
        XCTAssertTrue(profile.rmsEnvelope.allSatisfy { abs($0 - 0.5) < 1e-6 })
        // Audio shorter than the video pads the envelope with zeros instead of shortening it.
        let shorter = AudioAnalysis.profile(channels: [constant], sampleRate: 48_000, duration: 2.5)
        XCTAssertEqual(shorter.rmsEnvelope.count, 25)
        XCTAssertEqual(shorter.rmsEnvelope.last, 0)
    }
}
