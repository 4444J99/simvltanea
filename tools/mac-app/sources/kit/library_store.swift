import Foundation

/// Write-then-rename that also works when the destination does not exist yet, which is the state of
/// a fresh library's manifest and of a first Photos index.
public enum AtomicFile {
    public static func write(_ data: Data, to destination: URL) throws {
        try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        let staging = destination.deletingLastPathComponent().appendingPathComponent(".incoming-\(UUID().uuidString)")
        try data.write(to: staging)
        do {
            if FileManager.default.fileExists(atPath: destination.path) {
                _ = try FileManager.default.replaceItemAt(destination, withItemAt: staging)
            } else {
                try FileManager.default.moveItem(at: staging, to: destination)
            }
        } catch {
            try? FileManager.default.removeItem(at: staging)
            throw error
        }
    }
}

/// A private clip library on disk in exactly the shape the Studio and `stage_library_site` accept:
///
///     <root>/library/manifest.json
///     <root>/library/clips/<id>.mp4
///
/// Bookkeeping that is not part of that contract (the Photos import index) lives beside `library/`,
/// never inside it, because the Python checker refuses foreign entries in the library directory.
public final class LibraryStore {
    public let root: URL
    public var libraryDirectory: URL { root.appendingPathComponent("library", isDirectory: true) }
    public var clipsDirectory: URL { libraryDirectory.appendingPathComponent("clips", isDirectory: true) }
    public var manifestURL: URL { libraryDirectory.appendingPathComponent("manifest.json") }
    public var photosIndexURL: URL { root.appendingPathComponent("photos_index.json") }

    public init(root: URL) { self.root = root }

    public func loadManifest() throws -> LibraryManifest? {
        guard FileManager.default.fileExists(atPath: manifestURL.path) else { return nil }
        let manifest = try JSONDecoder().decode(LibraryManifest.self, from: Data(contentsOf: manifestURL))
        try manifest.validate()
        return manifest
    }

    /// Hash and copy one finished MP4 into `clips/`, returning the manifest entry it earns.
    /// An identical file already present is reused, never rewritten.
    public func ingest(file: URL, facts: MediaFacts, tags: [String: String] = [:]) throws -> ClipAsset {
        let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
        let bytes = (attributes[.size] as? NSNumber)?.intValue ?? 0
        guard bytes > 0, bytes <= LibraryLimits.maxClipBytes else {
            throw LibraryError("\(file.lastPathComponent) is \(bytes) bytes; the library takes 1 to \(LibraryLimits.maxClipBytes)")
        }
        let id = try ContentID.of(fileAt: file)
        let asset = ClipAsset(id: id, width: facts.width, height: facts.height, bytes: bytes,
                              durationSeconds: facts.duration, audio: facts.audio, tags: tags)
        try asset.validate(where: file.lastPathComponent)
        try FileManager.default.createDirectory(at: clipsDirectory, withIntermediateDirectories: true)
        let destination = libraryDirectory.appendingPathComponent(asset.file)
        if !FileManager.default.fileExists(atPath: destination.path) {
            let staging = clipsDirectory.appendingPathComponent(".incoming-\(UUID().uuidString)")
            try FileManager.default.copyItem(at: file, to: staging)
            try FileManager.default.moveItem(at: staging, to: destination)
        }
        return asset
    }

    /// Merge new assets into the stored manifest (new facts win for a repeated id) and write it
    /// atomically; every listed clip must exist and match its recorded size.
    @discardableResult
    public func commit(_ assets: [ClipAsset]) throws -> LibraryManifest {
        var byID: [String: ClipAsset] = [:]
        for clip in try loadManifest()?.clips ?? [] { byID[clip.id] = clip }
        for clip in assets { byID[clip.id] = clip }
        let manifest = LibraryManifest(clips: Array(byID.values))
        try manifest.validate()
        try verifyClips(manifest)
        try FileManager.default.createDirectory(at: libraryDirectory, withIntermediateDirectories: true)
        try AtomicFile.write(try manifest.encoded(), to: manifestURL)
        return manifest
    }

    func verifyClips(_ manifest: LibraryManifest) throws {
        for clip in manifest.clips {
            let path = libraryDirectory.appendingPathComponent(clip.file).path
            guard let attributes = try? FileManager.default.attributesOfItem(atPath: path),
                  (attributes[.size] as? NSNumber)?.intValue == clip.bytes else {
                throw LibraryError("clip \(clip.id) is missing or does not match its recorded size")
            }
        }
    }

    /// The full integrity check the Python stager performs: sizes, content hashes and no strays.
    public func verify() throws -> LibraryManifest {
        guard let manifest = try loadManifest() else { throw LibraryError("library has no manifest.json") }
        try verifyClips(manifest)
        let listed = Set(manifest.clips.map { "\($0.id).mp4" })
        let present = try FileManager.default.contentsOfDirectory(atPath: clipsDirectory.path)
        let strays = present.filter { !listed.contains($0) }
        guard strays.isEmpty else { throw LibraryError("library clips/ holds \(strays.count) files the manifest does not list") }
        for clip in manifest.clips {
            let id = try ContentID.of(fileAt: libraryDirectory.appendingPathComponent(clip.file))
            guard id == clip.id else { throw LibraryError("library clip content does not match its manifest id") }
        }
        return manifest
    }

    /// Import every `.mp4`/`.mov`/`.m4v` in a folder. Files the library cannot take are reported, not fatal.
    public func importFolder(_ folder: URL, transcode: (URL) async throws -> URL) async throws -> (added: [ClipAsset], skipped: [String]) {
        let names = try FileManager.default.contentsOfDirectory(atPath: folder.path).sorted()
            .filter { ["mp4", "mov", "m4v"].contains(($0 as NSString).pathExtension.lowercased()) && !$0.hasPrefix(".") }
        var added: [ClipAsset] = [], skipped: [String] = []
        for name in names {
            do {
                let ready = try await transcode(folder.appendingPathComponent(name))
                let facts = try await MediaProbe.facts(of: ready)
                added.append(try ingest(file: ready, facts: facts))
            } catch {
                skipped.append("\(name): \(error)")
            }
        }
        if !added.isEmpty { try commit(added) }
        return (added, skipped)
    }
}
