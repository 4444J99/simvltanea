import Foundation
import Network
@testable import SimvltaneaKit

final class ServerTests: XCTestCase {
    var work: URL!
    var server: LocalSiteServer!
    let clip = Data((0..<5000).map { UInt8($0 % 251) })

    override func setUpWithError() throws {
        work = FileManager.default.temporaryDirectory.appendingPathComponent("simv-srv-\(UUID().uuidString)")
        let studio = work.appendingPathComponent("studio"), library = work.appendingPathComponent("library/clips")
        try FileManager.default.createDirectory(at: studio, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: library, withIntermediateDirectories: true)
        try Data("<html>studio</html>".utf8).write(to: studio.appendingPathComponent("index.html"))
        try Data("// js".utf8).write(to: studio.appendingPathComponent("studio.js"))
        try Data("secret".utf8).write(to: work.appendingPathComponent("outside.txt"))
        try Data("{}".utf8).write(to: work.appendingPathComponent("library/manifest.json"))
        try clip.write(to: library.appendingPathComponent("aaaaaaaaaaaa.mp4"))
        try FileManager.default.createSymbolicLink(at: studio.appendingPathComponent("leak.txt"), withDestinationURL: work.appendingPathComponent("outside.txt"))
        server = LocalSiteServer(mounts: [.init(prefix: "", directory: studio), .init(prefix: "library", directory: work.appendingPathComponent("library"))])
        try server.start()
    }

    override func tearDown() { server.stop(); try? FileManager.default.removeItem(at: work) }

    func fetch(_ path: String, method: String = "GET", range: String? = nil) async throws -> (Data, HTTPURLResponse) {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:\(server.port)\(path)")!)
        request.httpMethod = method
        if let range { request.setValue(range, forHTTPHeaderField: "Range") }
        let (data, response) = try await URLSession(configuration: .ephemeral).data(for: request)
        return (data, response as! HTTPURLResponse)
    }

    func testServesTheStudioAndTheLibraryWithTheirTypes() async throws {
        var (data, response) = try await fetch("/")
        XCTAssertEqual(response.statusCode, 200); XCTAssertEqual(String(decoding: data, as: UTF8.self), "<html>studio</html>")
        XCTAssertTrue(response.value(forHTTPHeaderField: "Content-Type")!.hasPrefix("text/html"))
        (data, response) = try await fetch("/studio.js")
        XCTAssertTrue(response.value(forHTTPHeaderField: "Content-Type")!.hasPrefix("text/javascript"))
        (data, response) = try await fetch("/library/manifest.json")
        XCTAssertEqual(response.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(response.value(forHTTPHeaderField: "Cache-Control"), "no-store")
        (data, response) = try await fetch("/library/clips/aaaaaaaaaaaa.mp4")
        XCTAssertEqual(data, clip); XCTAssertEqual(response.value(forHTTPHeaderField: "Content-Type"), "video/mp4")
        XCTAssertEqual(response.value(forHTTPHeaderField: "Accept-Ranges"), "bytes")
    }

    func testRangeRequestsReturnExactlyTheRequestedBytes() async throws {
        var (data, response) = try await fetch("/library/clips/aaaaaaaaaaaa.mp4", range: "bytes=100-199")
        XCTAssertEqual(response.statusCode, 206); XCTAssertEqual(data, clip[100...199])
        XCTAssertEqual(response.value(forHTTPHeaderField: "Content-Range"), "bytes 100-199/5000")
        (data, response) = try await fetch("/library/clips/aaaaaaaaaaaa.mp4", range: "bytes=4900-")
        XCTAssertEqual(data, clip[4900...]); XCTAssertEqual(response.statusCode, 206)
        (data, response) = try await fetch("/library/clips/aaaaaaaaaaaa.mp4", range: "bytes=-50")
        XCTAssertEqual(data, clip[4950...])
        (data, response) = try await fetch("/library/clips/aaaaaaaaaaaa.mp4", range: "bytes=0-999999")
        XCTAssertEqual(data.count, 5000)
        (_, response) = try await fetch("/library/clips/aaaaaaaaaaaa.mp4", range: "bytes=9000-")
        XCTAssertEqual(response.statusCode, 416)
        XCTAssertEqual(response.value(forHTTPHeaderField: "Content-Range"), "bytes */5000")
        // A large chunked body crosses the 256 KiB streaming boundary intact.
        let big = Data((0..<700_000).map { UInt8($0 % 249) })
        try big.write(to: work.appendingPathComponent("library/clips/bbbbbbbbbbbb.mp4"))
        (data, _) = try await fetch("/library/clips/bbbbbbbbbbbb.mp4")
        XCTAssertEqual(data, big)
    }

    func testHeadMethodsAndMissingFilesBehave() async throws {
        var (data, response) = try await fetch("/library/clips/aaaaaaaaaaaa.mp4", method: "HEAD")
        XCTAssertEqual(response.statusCode, 200); XCTAssertTrue(data.isEmpty)
        XCTAssertEqual(response.value(forHTTPHeaderField: "Content-Length"), "5000")
        (_, response) = try await fetch("/library/clips/missing.mp4"); XCTAssertEqual(response.statusCode, 404)
        (_, response) = try await fetch("/", method: "POST"); XCTAssertEqual(response.statusCode, 405)
    }

    func testTraversalHiddenFilesAndSymlinkEscapesAreRefused() {
        for hostile in ["/../outside.txt", "/library/../outside.txt", "/library/clips/../../outside.txt", "//etc/passwd", "/.hidden",
                        "/%2e%2e/outside.txt", "/library", "/leak.txt", "relative"] {
            let path = LocalSiteServer.parse("GET \(hostile) HTTP/1.1")?.path ?? hostile
            XCTAssertNil(server.resolveForTesting(path), hostile)
        }
        XCTAssertNotNil(server.resolveForTesting("/library/manifest.json"))
        XCTAssertNotNil(server.resolveForTesting("/studio.js"))
    }

    func testRangeParserRejectsMalformedAndMultipleRanges() {
        XCTAssertNil(LocalSiteServer.byteRange("bytes=1-2,5-6", size: 10))
        XCTAssertNil(LocalSiteServer.byteRange("items=1-2", size: 10))
        XCTAssertNil(LocalSiteServer.byteRange("bytes=5-2", size: 10))
        XCTAssertNil(LocalSiteServer.byteRange("bytes=abc-", size: 10))
        XCTAssertEqual(LocalSiteServer.byteRange("bytes=2-4", size: 10), 2...4)
    }
}

extension LocalSiteServer {
    func resolveForTesting(_ path: String) -> URL? { resolve(path) }
}
