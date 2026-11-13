import AVFoundation
import CoreVideo
import Foundation

/// Writes a small real H.264/AAC MP4 so the probe, hashing and library paths run on genuine media.
enum FixtureVideo {
    static func write(to url: URL, width: Int, height: Int, seconds: Double, tone: Double?, amplitude: Float = 0.5,
                      rotate: Bool = false) async throws {
        try? FileManager.default.removeItem(at: url)
        let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
        let video = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: width, AVVideoHeightKey: height])
        if rotate { video.transform = CGAffineTransform(rotationAngle: .pi / 2) }
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: video, sourcePixelBufferAttributes: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String: width, kCVPixelBufferHeightKey as String: height])
        writer.add(video)
        var audio: AVAssetWriterInput?
        if tone != nil {
            let input = AVAssetWriterInput(mediaType: .audio, outputSettings: [
                AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48_000, AVNumberOfChannelsKey: 2, AVEncoderBitRateKey: 128_000])
            writer.add(input); audio = input
        }
        guard writer.startWriting() else { throw writer.error ?? NSError(domain: "fixture", code: 1) }
        writer.startSession(atSourceTime: .zero)
        let fps = 30, frames = Int((seconds * Double(fps)).rounded())
        let rate = 48_000.0, total = Int(seconds * rate), chunk = 4800
        var frame = 0, position = 0
        // Interleave both tracks: a writer withholds readiness from one input until the other catches up.
        while frame < frames || (audio != nil && position < total) {
            var progressed = false
            if frame < frames, video.isReadyForMoreMediaData {
                var buffer: CVPixelBuffer?
                CVPixelBufferCreate(nil, width, height, kCVPixelFormatType_32BGRA, nil, &buffer)
                guard let pixels = buffer else { throw NSError(domain: "fixture", code: 2) }
                CVPixelBufferLockBaseAddress(pixels, [])
                if let base = CVPixelBufferGetBaseAddress(pixels) {
                    memset(base, Int32((40 + frame * 7) % 256), CVPixelBufferGetBytesPerRow(pixels) * height)
                }
                CVPixelBufferUnlockBaseAddress(pixels, [])
                adaptor.append(pixels, withPresentationTime: CMTime(value: CMTimeValue(frame), timescale: CMTimeScale(fps)))
                frame += 1; progressed = true
                if frame == frames { video.markAsFinished() }
            }
            if let audio, let tone, position < total, audio.isReadyForMoreMediaData {
                let count = min(chunk, total - position)
                var samples = [Float](repeating: 0, count: count * 2)
                for index in 0..<count {
                    let value = amplitude * Float(sin(2 * Double.pi * tone * Double(position + index) / rate))
                    samples[index * 2] = value; samples[index * 2 + 1] = value
                }
                audio.append(try sampleBuffer(samples: samples, frames: count, start: position))
                position += count; progressed = true
                if position >= total { audio.markAsFinished() }
            }
            if !progressed { try await Task.sleep(nanoseconds: 2_000_000) }
        }
        await writer.finishWriting()
        if writer.status != .completed { throw writer.error ?? NSError(domain: "fixture", code: 3) }
    }

    static func sampleBuffer(samples: [Float], frames: Int, start: Int) throws -> CMSampleBuffer {
        var description = AudioStreamBasicDescription(
            mSampleRate: 48_000, mFormatID: kAudioFormatLinearPCM,
            mFormatFlags: kAudioFormatFlagIsFloat | kAudioFormatFlagIsPacked, mBytesPerPacket: 8, mFramesPerPacket: 1,
            mBytesPerFrame: 8, mChannelsPerFrame: 2, mBitsPerChannel: 32, mReserved: 0)
        var format: CMAudioFormatDescription?
        CMAudioFormatDescriptionCreate(allocator: nil, asbd: &description, layoutSize: 0, layout: nil, magicCookieSize: 0,
                                       magicCookie: nil, extensions: nil, formatDescriptionOut: &format)
        var block: CMBlockBuffer?
        let length = samples.count * MemoryLayout<Float>.size
        CMBlockBufferCreateWithMemoryBlock(allocator: nil, memoryBlock: nil, blockLength: length, blockAllocator: nil,
                                           customBlockSource: nil, offsetToData: 0, dataLength: length, flags: 0, blockBufferOut: &block)
        samples.withUnsafeBytes { raw in
            _ = CMBlockBufferReplaceDataBytes(with: raw.baseAddress!, blockBuffer: block!, offsetIntoDestination: 0, dataLength: length)
        }
        var buffer: CMSampleBuffer?
        CMAudioSampleBufferCreateReadyWithPacketDescriptions(
            allocator: nil, dataBuffer: block!, formatDescription: format!, sampleCount: frames,
            presentationTimeStamp: CMTime(value: CMTimeValue(start), timescale: 48_000), packetDescriptions: nil, sampleBufferOut: &buffer)
        guard let result = buffer else { throw NSError(domain: "fixture", code: 4) }
        return result
    }
}
