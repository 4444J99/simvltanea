import Foundation

/// What the Studio's sound layer reads for each clip: presence, loudness, peak and a 10 Hz envelope.
public struct AudioProfile: Equatable {
    public var hasAudio: Bool
    public var lufsIntegrated: Double?
    public var peakDbfs: Double?
    public var rmsEnvelope: [Double]

    public static func silent(duration: Double) -> AudioProfile {
        AudioProfile(hasAudio: false, lufsIntegrated: nil, peakDbfs: nil,
                     rmsEnvelope: [Double](repeating: 0, count: envelopeCount(duration: duration)))
    }

    public static func envelopeCount(duration: Double) -> Int {
        Int((duration * Double(LibraryLimits.envelopeHz)).rounded(.up))
    }
}

/// ITU-R BS.1770-4 integrated loudness with the EBU R128 gates, plus peak and RMS envelope.
/// Input is de-interleaved Float PCM, one array per channel.
public enum AudioAnalysis {
    struct Biquad {
        var b0, b1, b2, a1, a2: Double
        func run(_ input: [Double]) -> [Double] {
            var out = [Double](repeating: 0, count: input.count)
            var x1 = 0.0, x2 = 0.0, y1 = 0.0, y2 = 0.0
            for index in 0..<input.count {
                let x = input[index]
                let y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                out[index] = y
                x2 = x1; x1 = x; y2 = y1; y1 = y
            }
            return out
        }
    }

    /// The two K-weighting stages for any sample rate (the published 48 kHz coefficients are one case).
    static func kWeighting(sampleRate: Double) -> [Biquad] {
        let shelfGain = 3.999843853973347, shelfQ = 0.7071752369554196, shelfFc = 1681.9744509555319
        var k = tan(Double.pi * shelfFc / sampleRate)
        let vh = pow(10, shelfGain / 20), vb = pow(vh, 0.4996667741545416)
        var a0 = 1 + k / shelfQ + k * k
        let shelf = Biquad(b0: (vh + vb * k / shelfQ + k * k) / a0, b1: 2 * (k * k - vh) / a0,
                           b2: (vh - vb * k / shelfQ + k * k) / a0,
                           a1: 2 * (k * k - 1) / a0, a2: (1 - k / shelfQ + k * k) / a0)
        let highpassQ = 0.5003270373238773, highpassFc = 38.13547087602444
        k = tan(Double.pi * highpassFc / sampleRate)
        a0 = 1 + k / highpassQ + k * k
        let highpass = Biquad(b0: 1, b1: -2, b2: 1, a1: 2 * (k * k - 1) / a0, a2: (1 - k / highpassQ + k * k) / a0)
        return [shelf, highpass]
    }

    public static func profile(channels: [[Float]], sampleRate: Double, duration: Double) -> AudioProfile {
        guard !channels.isEmpty, sampleRate > 0, channels.allSatisfy({ !$0.isEmpty }) else {
            return .silent(duration: duration)
        }
        var peak = 0.0
        for channel in channels { for sample in channel { peak = max(peak, Double(abs(sample))) } }
        let peakDb = peak > 0 ? max(-160, min(24, 20 * log10(peak))) : -160
        return AudioProfile(hasAudio: true,
                            lufsIntegrated: integratedLoudness(channels: channels, sampleRate: sampleRate),
                            peakDbfs: peakDb,
                            rmsEnvelope: envelope(channels: channels, sampleRate: sampleRate, duration: duration))
    }

    /// Mean-square across channels per 100 ms window, as RMS clamped to 0...1; zero past the audio's end.
    public static func envelope(channels: [[Float]], sampleRate: Double, duration: Double) -> [Double] {
        let count = AudioProfile.envelopeCount(duration: duration)
        let window = sampleRate / Double(LibraryLimits.envelopeHz)
        var out = [Double](repeating: 0, count: count)
        let frames = channels.map(\.count).min() ?? 0
        for index in 0..<count {
            let start = Int((Double(index) * window).rounded()), end = min(frames, Int((Double(index + 1) * window).rounded()))
            guard start < end else { continue }
            var sum = 0.0
            for channel in channels { for sample in channel[start..<end] { sum += Double(sample) * Double(sample) } }
            out[index] = min(1, max(0, (sum / Double((end - start) * channels.count)).squareRoot()))
        }
        return out
    }

    public static func integratedLoudness(channels: [[Float]], sampleRate: Double) -> Double? {
        let stages = kWeighting(sampleRate: sampleRate)
        // BS.1770 weights: left, right and centre 1.0; surrounds 1.41. Mono uses a single channel.
        let weights: [Double] = channels.indices.map { $0 >= 4 ? 1.41 : 1.0 }
        let weighted: [[Double]] = channels.map { channel in
            stages.reduce(channel.map(Double.init)) { signal, stage in stage.run(signal) }
        }
        let block = Int((0.4 * sampleRate).rounded()), step = Int((0.1 * sampleRate).rounded())
        let frames = weighted.map(\.count).min() ?? 0
        guard block > 0, step > 0, frames >= block else { return nil }
        var energies: [Double] = []
        var start = 0
        while start + block <= frames {
            var total = 0.0
            for (index, channel) in weighted.enumerated() {
                var sum = 0.0
                for sample in channel[start..<(start + block)] { sum += sample * sample }
                total += weights[index] * sum / Double(block)
            }
            energies.append(total)
            start += step
        }
        func loudness(_ energy: Double) -> Double { -0.691 + 10 * log10(energy) }
        let absolute = energies.filter { $0 > 0 && loudness($0) > -70 }
        guard !absolute.isEmpty else { return nil }
        let relativeGate = loudness(absolute.reduce(0, +) / Double(absolute.count)) - 10
        let gated = absolute.filter { loudness($0) > relativeGate }
        guard !gated.isEmpty else { return nil }
        let result = loudness(gated.reduce(0, +) / Double(gated.count))
        return result.isFinite ? max(-160, min(12, result)) : nil
    }
}
