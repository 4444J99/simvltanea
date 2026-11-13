import AVFoundation
import Foundation

public struct MediaFacts: Equatable {
    public var width: Int
    public var height: Int
    public var duration: Double
    public var audio: AudioProfile
}

/// Reads display size, duration and the audio profile of a local video with AVFoundation.
public enum MediaProbe {
    /// Durations are kept to milliseconds so the manifest, the envelope length and the Studio agree.
    public static func roundedDuration(_ seconds: Double) -> Double { (seconds * 1000).rounded() / 1000 }

    /// Display size in pixels, with the track's rotation applied.
    public static func displaySize(of url: URL) async throws -> (Int, Int) {
        let asset = AVURLAsset(url: url)
        guard let video = try await asset.loadTracks(withMediaType: .video).first else {
            throw LibraryError("\(url.lastPathComponent) has no video track")
        }
        let size = try await video.load(.naturalSize)
        let shown = size.applying(try await video.load(.preferredTransform))
        return (Int(abs(shown.width).rounded()), Int(abs(shown.height).rounded()))
    }

    public static func facts(of url: URL) async throws -> MediaFacts {
        let asset = AVURLAsset(url: url)
        let (width, height) = try await displaySize(of: url)
        let duration = roundedDuration(try await asset.load(.duration).seconds)
        guard duration.isFinite, duration > 0 else { throw LibraryError("\(url.lastPathComponent) has no duration") }
        let audio = try await audioProfile(asset: asset, duration: duration)
        return MediaFacts(width: width, height: height, duration: duration, audio: audio)
    }

    static func audioProfile(asset: AVURLAsset, duration: Double) async throws -> AudioProfile {
        let tracks = try await asset.loadTracks(withMediaType: .audio)
        guard let track = tracks.first else { return .silent(duration: duration) }
        let reader = try AVAssetReader(asset: asset)
        let sampleRate = 48_000.0
        let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVLinearPCMBitDepthKey: 32,
            AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false,
            AVSampleRateKey: sampleRate,
            AVNumberOfChannelsKey: 2,
        ])
        guard reader.canAdd(output) else { throw LibraryError("audio track cannot be decoded") }
        reader.add(output)
        guard reader.startReading() else { throw LibraryError("audio read failed: \(reader.error?.localizedDescription ?? "unknown")") }
        var timeline = AudioTimeline(sampleRate: sampleRate)
        while let buffer = output.copyNextSampleBuffer() {
            guard let block = CMSampleBufferGetDataBuffer(buffer) else { continue }
            let length = CMBlockBufferGetDataLength(block)
            var data = [Float](repeating: 0, count: length / MemoryLayout<Float>.size)
            let status = data.withUnsafeMutableBytes { raw in
                CMBlockBufferCopyDataBytes(block, atOffset: 0, dataLength: length, destination: raw.baseAddress!)
            }
            guard status == kCMBlockBufferNoErr else { throw LibraryError("audio buffer could not be copied") }
            let start = CMSampleBufferGetPresentationTimeStamp(buffer).seconds
            timeline.append(interleaved: data, startSeconds: start.isFinite ? start : nil)
        }
        if reader.status == .failed { throw LibraryError("audio read failed: \(reader.error?.localizedDescription ?? "unknown")") }
        guard !timeline.left.isEmpty else { return .silent(duration: duration) }
        return AudioAnalysis.profile(channels: [timeline.left, timeline.right], sampleRate: sampleRate, duration: duration)
    }
}

/// Collects decoded stereo audio on the clip's own timeline. The Studio indexes the envelope by
/// `currentTime`, so audio that starts late or has gaps must keep its silence instead of being
/// packed against time zero.
public struct AudioTimeline {
    public let sampleRate: Double
    public private(set) var left: [Float] = []
    public private(set) var right: [Float] = []

    public init(sampleRate: Double) { self.sampleRate = sampleRate }

    /// `interleaved` holds L,R pairs. A start time later than the audio so far is padded with zeros;
    /// one that overlaps what is already held drops the overlapping frames.
    public mutating func append(interleaved: [Float], startSeconds: Double?) {
        var skip = 0
        if let startSeconds {
            let wanted = max(0, Int((startSeconds * sampleRate).rounded()))
            if wanted > left.count {
                let gap = wanted - left.count
                left.append(contentsOf: repeatElement(0, count: gap)); right.append(contentsOf: repeatElement(0, count: gap))
            } else { skip = left.count - wanted }
        }
        var index = skip * 2
        while index + 1 < interleaved.count { left.append(interleaved[index]); right.append(interleaved[index + 1]); index += 2 }
    }
}
