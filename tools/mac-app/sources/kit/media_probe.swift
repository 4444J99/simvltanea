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

    public static func facts(of url: URL) async throws -> MediaFacts {
        let asset = AVURLAsset(url: url)
        let videos = try await asset.loadTracks(withMediaType: .video)
        guard let video = videos.first else { throw LibraryError("\(url.lastPathComponent) has no video track") }
        let size = try await video.load(.naturalSize)
        let transform = try await video.load(.preferredTransform)
        let shown = size.applying(transform)
        let width = Int(abs(shown.width).rounded()), height = Int(abs(shown.height).rounded())
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
        var left: [Float] = [], right: [Float] = []
        left.reserveCapacity(Int(duration * sampleRate)); right.reserveCapacity(Int(duration * sampleRate))
        while let buffer = output.copyNextSampleBuffer() {
            guard let block = CMSampleBufferGetDataBuffer(buffer) else { continue }
            let length = CMBlockBufferGetDataLength(block)
            var data = [Float](repeating: 0, count: length / MemoryLayout<Float>.size)
            let status = data.withUnsafeMutableBytes { raw in
                CMBlockBufferCopyDataBytes(block, atOffset: 0, dataLength: length, destination: raw.baseAddress!)
            }
            guard status == kCMBlockBufferNoErr else { throw LibraryError("audio buffer could not be copied") }
            var index = 0
            while index + 1 < data.count { left.append(data[index]); right.append(data[index + 1]); index += 2 }
        }
        if reader.status == .failed { throw LibraryError("audio read failed: \(reader.error?.localizedDescription ?? "unknown")") }
        guard !left.isEmpty else { return .silent(duration: duration) }
        return AudioAnalysis.profile(channels: [left, right], sampleRate: sampleRate, duration: duration)
    }
}
