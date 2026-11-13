import AVFoundation
import Foundation

/// Turns an arbitrary local video into an MP4 the library accepts (at most 64 MiB, at most 4096 px).
public enum ClipTranscoder {
    public static let presets = [AVAssetExportPreset1920x1080, AVAssetExportPreset1280x720, AVAssetExportPreset640x480]

    /// Returns the input unchanged when it already fits, otherwise a re-encoded copy in `scratch`.
    public static func prepare(_ source: URL, scratch: URL) async throws -> URL {
        if source.pathExtension.lowercased() == "mp4", try fits(source) { return source }
        return try await export(asset: AVURLAsset(url: source), scratch: scratch)
    }

    static func fits(_ url: URL) throws -> Bool {
        let bytes = (try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.intValue ?? 0
        return bytes > 0 && bytes <= LibraryLimits.maxClipBytes
    }

    /// Try each preset from large to small until one fits the library's size bound.
    public static func export(asset: AVAsset, scratch: URL) async throws -> URL {
        try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
        var lastError: Error = LibraryError("no export preset produced a usable clip")
        for preset in presets {
            guard let session = AVAssetExportSession(asset: asset, presetName: preset) else { continue }
            let target = scratch.appendingPathComponent("\(UUID().uuidString).mp4")
            session.outputURL = target
            session.outputFileType = .mp4
            session.shouldOptimizeForNetworkUse = true
            await withCheckedContinuation { (done: CheckedContinuation<Void, Never>) in
                session.exportAsynchronously { done.resume() }
            }
            if session.status == .completed, try fits(target) { return target }
            lastError = session.error ?? LibraryError("export at \(preset) exceeded the clip size bound")
            try? FileManager.default.removeItem(at: target)
        }
        throw lastError
    }
}
