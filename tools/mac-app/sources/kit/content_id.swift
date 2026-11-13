import CryptoKit
import Foundation

/// The library names every file by the first 12 hex digits of its SHA-256, which the Studio
/// re-checks with `crypto.subtle` before it trusts a clip.
public enum ContentID {
    public static func of(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined().prefix(12).description
    }

    /// Hash a file in bounded chunks so a 64 MiB clip never needs one contiguous read.
    public static func of(fileAt url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let chunk = try handle.read(upToCount: 1 << 20), !chunk.isEmpty { hasher.update(data: chunk) }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined().prefix(12).description
    }
}
