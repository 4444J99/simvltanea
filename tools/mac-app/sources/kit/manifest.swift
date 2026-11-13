import Foundation

/// The `simvltanea.public-demo/1` library document the Studio reads from `library/manifest.json`.
/// Bounds mirror `tools/publishing/stage_library_site.py`; `tests/kit` and the Python contract test
/// keep the two in step.
public enum LibraryLimits {
    public static let schema = "simvltanea.public-demo/1"
    public static let maxClips = 5000
    public static let maxClipBytes = 64 * 1024 * 1024
    public static let maxSide = 4096
    public static let minSeconds = 0.25
    public static let maxSeconds = 600.0
    public static let envelopeHz = 10
}

public struct LibraryError: Error, CustomStringConvertible, Equatable {
    public let message: String
    public init(_ message: String) { self.message = message }
    public var description: String { message }
}

public struct ClipAsset: Codable, Equatable {
    public var id: String
    public var file: String
    public var width: Int
    public var height: Int
    public var orientation: String
    public var bytes: Int
    public var durationSeconds: Double
    public var hasAudio: Bool
    public var lufsIntegrated: Double?
    public var peakDbfs: Double?
    public var envelopeHz: Int
    public var rmsEnvelope: [Double]
    public var tags: [String: String]

    enum CodingKeys: String, CodingKey {
        case id, file, width, height, orientation, bytes, tags
        case durationSeconds = "duration_seconds"
        case hasAudio = "has_audio"
        case lufsIntegrated = "lufs_integrated"
        case peakDbfs = "peak_dbfs"
        case envelopeHz = "envelope_hz"
        case rmsEnvelope = "rms_envelope"
    }

    public init(id: String, width: Int, height: Int, bytes: Int, durationSeconds: Double,
                audio: AudioProfile, tags: [String: String] = [:]) {
        self.id = id
        self.file = "clips/\(id).mp4"
        self.width = width
        self.height = height
        self.orientation = height > width ? "portrait" : "landscape"
        self.bytes = bytes
        self.durationSeconds = durationSeconds
        self.hasAudio = audio.hasAudio
        self.lufsIntegrated = audio.lufsIntegrated
        self.peakDbfs = audio.peakDbfs
        self.envelopeHz = LibraryLimits.envelopeHz
        self.rmsEnvelope = audio.rmsEnvelope
        self.tags = tags
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(file, forKey: .file)
        try container.encode(width, forKey: .width)
        try container.encode(height, forKey: .height)
        try container.encode(orientation, forKey: .orientation)
        try container.encode(bytes, forKey: .bytes)
        try container.encode(durationSeconds, forKey: .durationSeconds)
        try container.encode(hasAudio, forKey: .hasAudio)
        // Silence and unmeasurable loudness are explicit nulls, as the Python builder writes them.
        try container.encode(lufsIntegrated, forKey: .lufsIntegrated)
        try container.encode(peakDbfs, forKey: .peakDbfs)
        try container.encode(envelopeHz, forKey: .envelopeHz)
        try container.encode(rmsEnvelope, forKey: .rmsEnvelope)
        try container.encode(tags, forKey: .tags)
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        file = try container.decode(String.self, forKey: .file)
        width = try container.decode(Int.self, forKey: .width)
        height = try container.decode(Int.self, forKey: .height)
        orientation = try container.decode(String.self, forKey: .orientation)
        bytes = try container.decode(Int.self, forKey: .bytes)
        durationSeconds = try container.decode(Double.self, forKey: .durationSeconds)
        hasAudio = try container.decode(Bool.self, forKey: .hasAudio)
        lufsIntegrated = try container.decodeIfPresent(Double.self, forKey: .lufsIntegrated)
        peakDbfs = try container.decodeIfPresent(Double.self, forKey: .peakDbfs)
        envelopeHz = try container.decode(Int.self, forKey: .envelopeHz)
        rmsEnvelope = try container.decode([Double].self, forKey: .rmsEnvelope)
        tags = try container.decodeIfPresent([String: String].self, forKey: .tags) ?? [:]
    }

    /// Throws the first rule this clip breaks, with the same wording class as the Python validator.
    public func validate(where location: String = "clip") throws {
        let hex = Set("0123456789abcdef")
        guard id.count == 12, id.allSatisfy({ hex.contains($0) }) else {
            throw LibraryError("\(location): id must be 12 lowercase hex digits")
        }
        guard file == "clips/\(id).mp4" else { throw LibraryError("\(location): file must be clips/<id>.mp4") }
        guard (1...LibraryLimits.maxSide).contains(width), (1...LibraryLimits.maxSide).contains(height) else {
            throw LibraryError("\(location): width and height must be whole pixels up to \(LibraryLimits.maxSide)")
        }
        guard (1...LibraryLimits.maxClipBytes).contains(bytes) else {
            throw LibraryError("\(location): bytes must be a size up to \(LibraryLimits.maxClipBytes)")
        }
        let expected = height > width ? "portrait" : "landscape"
        guard orientation == expected else { throw LibraryError("\(location): orientation must be \(expected)") }
        guard durationSeconds.isFinite,
              durationSeconds >= LibraryLimits.minSeconds, durationSeconds <= LibraryLimits.maxSeconds else {
            throw LibraryError("\(location): duration_seconds must lie in 0.25..600")
        }
        if let loudness = lufsIntegrated, !(loudness.isFinite && loudness >= -160 && loudness <= 12) {
            throw LibraryError("\(location): lufs_integrated must be finite or null")
        }
        if hasAudio {
            guard let peak = peakDbfs, peak.isFinite, peak >= -160, peak <= 24 else {
                throw LibraryError("\(location): peak_dbfs must be finite for sound and null for silence")
            }
        } else {
            guard peakDbfs == nil else { throw LibraryError("\(location): peak_dbfs must be finite for sound and null for silence") }
            guard lufsIntegrated == nil else { throw LibraryError("\(location): silent integrated loudness must be null") }
        }
        guard envelopeHz == LibraryLimits.envelopeHz,
              rmsEnvelope.count == Int((durationSeconds * Double(LibraryLimits.envelopeHz)).rounded(.up)),
              rmsEnvelope.allSatisfy({ $0.isFinite && $0 >= 0 && $0 <= 1 }) else {
            throw LibraryError("\(location): rms_envelope must contain bounded 10 Hz samples for the duration")
        }
    }
}

public struct LibraryManifest: Codable, Equatable {
    public var schema: String
    public var clips: [ClipAsset]

    public init(clips: [ClipAsset]) {
        self.schema = LibraryLimits.schema
        self.clips = clips.sorted { $0.id < $1.id }
    }

    public func validate() throws {
        guard schema == LibraryLimits.schema else { throw LibraryError("library manifest schema must be \(LibraryLimits.schema)") }
        guard !clips.isEmpty, clips.count <= LibraryLimits.maxClips else {
            throw LibraryError("library manifest needs 1 to \(LibraryLimits.maxClips) clips")
        }
        var seen = Set<String>()
        for (number, clip) in clips.enumerated() {
            let location = "library manifest clip \(number + 1)"
            try clip.validate(where: location)
            guard seen.insert(clip.id).inserted else { throw LibraryError("\(location): duplicate id") }
        }
    }

    public func encoded() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .prettyPrinted, .withoutEscapingSlashes]
        return try encoder.encode(self) + Data("\n".utf8)
    }
}
