import Foundation

/// A Photos video as the planner sees it. PhotoKit values are copied into this struct so the
/// choice of what to import is pure, deterministic and testable without a Photos library.
public struct PhotoCandidate: Equatable {
    public var localIdentifier: String
    public var duration: Double
    public var pixelWidth: Int
    public var pixelHeight: Int
    public var created: Date?
    public var isFavorite: Bool

    public init(localIdentifier: String, duration: Double, pixelWidth: Int, pixelHeight: Int,
                created: Date? = nil, isFavorite: Bool = false) {
        self.localIdentifier = localIdentifier
        self.duration = duration
        self.pixelWidth = pixelWidth
        self.pixelHeight = pixelHeight
        self.created = created
        self.isFavorite = isFavorite
    }
}

public struct PhotoCriteria: Equatable {
    public var minSeconds = 1.0
    public var maxSeconds = 30.0
    public var favoritesOnly = false
    public var limit: Int?
    public init() {}
}

/// What was already taken or refused, kept beside the library so a re-run only does new work.
public struct PhotosIndex: Codable, Equatable {
    public var imported: [String: String] = [:]   // Photos local identifier -> clip id
    public var skipped: [String: String] = [:]    // Photos local identifier -> reason
    public init() {}

    public static func load(from url: URL) -> PhotosIndex {
        (try? JSONDecoder().decode(PhotosIndex.self, from: Data(contentsOf: url))) ?? PhotosIndex()
    }

    public func save(to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
        try AtomicFile.write(try encoder.encode(self), to: url)
    }
}

public enum ExportPlanner {
    /// Candidates inside the criteria that are new to the index, favourites first and then newest
    /// first, with the identifier as the final tie-break so the same library always plans the same way.
    public static func select(_ candidates: [PhotoCandidate], criteria: PhotoCriteria, index: PhotosIndex) -> [PhotoCandidate] {
        let wanted = candidates.filter { candidate in
            candidate.duration.isFinite
                && candidate.duration >= max(criteria.minSeconds, LibraryLimits.minSeconds)
                && candidate.duration <= min(criteria.maxSeconds, LibraryLimits.maxSeconds)
                && candidate.pixelWidth > 0 && candidate.pixelHeight > 0
                && (!criteria.favoritesOnly || candidate.isFavorite)
                && index.imported[candidate.localIdentifier] == nil
                && index.skipped[candidate.localIdentifier] == nil
        }
        let ordered = wanted.sorted { left, right in
            if left.isFavorite != right.isFavorite { return left.isFavorite }
            let (a, b) = (left.created ?? .distantPast, right.created ?? .distantPast)
            if a != b { return a > b }
            return left.localIdentifier < right.localIdentifier
        }
        guard let limit = criteria.limit else { return ordered }
        return Array(ordered.prefix(max(0, limit)))
    }
}

public struct ImportProgress: Equatable {
    public var done: Int
    public var total: Int
    public var added: Int
    public var skipped: Int
    public var failed: Int
}
