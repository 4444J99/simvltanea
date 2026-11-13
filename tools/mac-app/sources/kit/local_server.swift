import Foundation
import Network

/// Serves the staged Studio and the private library to the app's own web view on the loopback
/// interface. `127.0.0.1` is a secure context, which the Studio needs for `crypto.subtle`, and
/// video playback needs HTTP range support, which a custom URL scheme handler does not give.
public final class LocalSiteServer {
    public struct Mount {
        public var prefix: String   // "" for the Studio, "library" for the clip library
        public var directory: URL
        public init(prefix: String, directory: URL) { self.prefix = prefix; self.directory = directory }
    }

    private let mounts: [Mount]
    private let queue = DispatchQueue(label: "simvltanea.local-site")
    private var listener: NWListener?
    public private(set) var port: UInt16 = 0

    public init(mounts: [Mount]) {
        // Longest prefix first so "library" wins over the Studio root.
        self.mounts = mounts.sorted { $0.prefix.count > $1.prefix.count }
    }

    public var baseURL: URL { URL(string: "http://127.0.0.1:\(port)/")! }

    public func start() throws {
        let parameters = NWParameters.tcp
        parameters.requiredInterfaceType = .loopback
        let listener = try NWListener(using: parameters, on: .any)
        let ready = DispatchSemaphore(value: 0)
        var failure: NWError?
        listener.stateUpdateHandler = { [weak listener] state in
            switch state {
            case .ready: self.port = listener?.port?.rawValue ?? 0; ready.signal()
            case .failed(let error): failure = error; ready.signal()
            default: break
            }
        }
        listener.newConnectionHandler = { [weak self] connection in self?.accept(connection) }
        listener.start(queue: queue)
        guard ready.wait(timeout: .now() + 5) == .success, failure == nil, port != 0 else {
            listener.cancel()
            throw LibraryError("the local site server did not start: \(failure.map(String.init(describing:)) ?? "timeout")")
        }
        self.listener = listener
    }

    public func stop() { listener?.cancel(); listener = nil }

    // MARK: connections

    private func accept(_ connection: NWConnection) {
        connection.start(queue: queue)
        receive(on: connection, buffered: Data())
    }

    private func receive(on connection: NWConnection, buffered: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 16 * 1024) { [weak self] data, _, complete, error in
            guard let self else { return }
            var buffer = buffered
            if let data { buffer.append(data) }
            if let end = buffer.range(of: Data("\r\n\r\n".utf8)) {
                let head = String(decoding: buffer[..<end.lowerBound], as: UTF8.self)
                self.respond(to: head, on: connection) { keepAlive in
                    if keepAlive { self.receive(on: connection, buffered: Data(buffer[end.upperBound...])) }
                    else { connection.cancel() }
                }
            } else if error != nil || complete || buffer.count > 64 * 1024 {
                connection.cancel()
            } else {
                self.receive(on: connection, buffered: buffer)
            }
        }
    }

    // MARK: HTTP

    struct Request {
        var method: String
        var path: String
        var range: String?
    }

    static func parse(_ head: String) -> Request? {
        let lines = head.components(separatedBy: "\r\n")
        let parts = lines.first?.split(separator: " ", omittingEmptySubsequences: true).map(String.init) ?? []
        guard parts.count == 3, parts[2].hasPrefix("HTTP/1.") else { return nil }
        var range: String?
        for line in lines.dropFirst() {
            if let colon = line.firstIndex(of: ":"), line[..<colon].lowercased() == "range" {
                range = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
            }
        }
        let target = parts[1].split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false).first.map(String.init) ?? ""
        return Request(method: parts[0], path: target.removingPercentEncoding ?? target, range: range)
    }

    /// Map a URL path to a file strictly inside a mount, or nil for anything else.
    func resolve(_ path: String) -> URL? {
        guard path.hasPrefix("/") else { return nil }
        var relative = String(path.dropFirst())
        if relative.isEmpty || relative.hasSuffix("/") { relative += "index.html" }
        let segments = relative.split(separator: "/", omittingEmptySubsequences: false).map(String.init)
        guard !segments.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." || $0.hasPrefix(".") || $0.contains("\0") }) else { return nil }
        for mount in mounts {
            let inside: [String]
            if mount.prefix.isEmpty { inside = segments }
            else if segments.first == mount.prefix, segments.count > 1 { inside = Array(segments.dropFirst()) }
            else { continue }
            let candidate = inside.reduce(mount.directory) { $0.appendingPathComponent($1) }
            let base = mount.directory.resolvingSymlinksInPath().path + "/"
            let real = candidate.resolvingSymlinksInPath()
            guard real.path.hasPrefix(base) else { return nil }
            var isDirectory: ObjCBool = false
            guard FileManager.default.fileExists(atPath: real.path, isDirectory: &isDirectory), !isDirectory.boolValue else {
                if mount.prefix.isEmpty { return nil }
                return nil
            }
            return real
        }
        return nil
    }

    static func contentType(_ url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "html": return "text/html; charset=utf-8"
        case "js": return "text/javascript; charset=utf-8"
        case "css": return "text/css; charset=utf-8"
        case "json": return "application/json"
        case "mp4", "m4v": return "video/mp4"
        case "svg": return "image/svg+xml"
        case "png": return "image/png"
        case "wasm": return "application/wasm"
        default: return "application/octet-stream"
        }
    }

    /// Parse a single `bytes=a-b`, `bytes=a-` or `bytes=-n` range against a known size.
    static func byteRange(_ header: String, size: Int) -> ClosedRange<Int>? {
        guard header.hasPrefix("bytes="), !header.contains(","), size > 0 else { return nil }
        let spec = header.dropFirst(6).split(separator: "-", maxSplits: 1, omittingEmptySubsequences: false).map(String.init)
        guard spec.count == 2 else { return nil }
        if spec[0].isEmpty {
            guard let suffix = Int(spec[1]), suffix > 0 else { return nil }
            return max(0, size - suffix)...(size - 1)
        }
        guard let first = Int(spec[0]), first < size else { return nil }
        let last = spec[1].isEmpty ? size - 1 : min(Int(spec[1]) ?? size - 1, size - 1)
        return first <= last ? first...last : nil
    }

    private func respond(to head: String, on connection: NWConnection, finished: @escaping (Bool) -> Void) {
        guard let request = Self.parse(head) else {
            return send(status: "400 Bad Request", on: connection, body: Data("bad request".utf8), keepAlive: false, finished: finished)
        }
        guard request.method == "GET" || request.method == "HEAD" else {
            return send(status: "405 Method Not Allowed", extra: ["Allow: GET, HEAD"], on: connection, body: Data(), keepAlive: false, finished: finished)
        }
        guard let file = resolve(request.path),
              let size = (try? FileManager.default.attributesOfItem(atPath: file.path)[.size] as? NSNumber)?.intValue else {
            return send(status: "404 Not Found", on: connection, body: Data("not found".utf8), keepAlive: true, finished: finished)
        }
        var headers = ["Content-Type: \(Self.contentType(file))", "Accept-Ranges: bytes", "Cache-Control: no-store",
                       "X-Content-Type-Options: nosniff"]
        var status = "200 OK", span = 0...max(0, size - 1)
        if let header = request.range {
            guard let range = Self.byteRange(header, size: size) else {
                return send(status: "416 Range Not Satisfiable", extra: ["Content-Range: bytes */\(size)"], on: connection, body: Data(), keepAlive: true, finished: finished)
            }
            span = range; status = "206 Partial Content"
            headers.append("Content-Range: bytes \(range.lowerBound)-\(range.upperBound)/\(size)")
        }
        let length = size == 0 ? 0 : span.count
        headers.append("Content-Length: \(length)")
        let headBytes = Data("HTTP/1.1 \(status)\r\n\(headers.joined(separator: "\r\n"))\r\n\r\n".utf8)
        guard request.method == "GET", length > 0 else {
            return connection.send(content: headBytes, completion: .contentProcessed { _ in finished(true) })
        }
        connection.send(content: headBytes, completion: .contentProcessed { [weak self] error in
            guard error == nil, let self else { return finished(false) }
            self.stream(file: file, from: span.lowerBound, count: length, on: connection, finished: finished)
        })
    }

    private func stream(file: URL, from offset: Int, count: Int, on connection: NWConnection, finished: @escaping (Bool) -> Void) {
        guard let handle = try? FileHandle(forReadingFrom: file) else { return finished(false) }
        func next(_ position: Int, _ remaining: Int) {
            guard remaining > 0 else { try? handle.close(); return finished(true) }
            let chunk: Data?
            do { try handle.seek(toOffset: UInt64(position)); chunk = try handle.read(upToCount: min(remaining, 256 * 1024)) }
            catch { chunk = nil }
            guard let chunk, !chunk.isEmpty else { try? handle.close(); return finished(false) }
            connection.send(content: chunk, completion: .contentProcessed { error in
                if error != nil { try? handle.close(); return finished(false) }
                next(position + chunk.count, remaining - chunk.count)
            })
        }
        next(offset, count)
    }

    private func send(status: String, extra: [String] = [], on connection: NWConnection, body: Data, keepAlive: Bool,
                      finished: @escaping (Bool) -> Void) {
        let headers = ["Content-Type: text/plain; charset=utf-8", "Content-Length: \(body.count)", "Cache-Control: no-store"] + extra
        let response = Data("HTTP/1.1 \(status)\r\n\(headers.joined(separator: "\r\n"))\r\n\r\n".utf8) + body
        connection.send(content: response, completion: .contentProcessed { error in finished(keepAlive && error == nil) })
    }
}
