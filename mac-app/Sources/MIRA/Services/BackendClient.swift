import Foundation

actor BackendClient {
    static let shared = BackendClient()

    private let base: URL
    private let session: URLSession

    init(base: URL = URL(string: "http://127.0.0.1:7842")!) {
        self.base = base
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 120
        config.timeoutIntervalForResource = 600
        self.session = URLSession(configuration: config)
    }

    struct ChatResponse: Decodable {
        let text: String
        let model_used: String
        let neurons_recalled: Int
    }

    func chat(text: String) async throws -> ChatResponse {
        var req = URLRequest(url: base.appendingPathComponent("chat"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["text": text, "stream": false]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(ChatResponse.self, from: data)
    }

    /// Stream a reply token-by-token. Yields plain text chunks; terminates
    /// when the server sends `[DONE]`.
    func chatStream(text: String) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    var req = URLRequest(url: base.appendingPathComponent("chat"))
                    req.httpMethod = "POST"
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    let body: [String: Any] = ["text": text, "stream": true]
                    req.httpBody = try JSONSerialization.data(withJSONObject: body)
                    let (bytes, response) = try await session.bytes(for: req)
                    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                        throw URLError(.badServerResponse)
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let chunk = String(line.dropFirst(6))
                        if chunk == "[DONE]" { break }
                        continuation.yield(chunk)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    func health() async -> Bool {
        var req = URLRequest(url: base.appendingPathComponent("health"))
        req.timeoutInterval = 2
        guard let (_, resp) = try? await session.data(for: req),
              let http = resp as? HTTPURLResponse, http.statusCode == 200 else {
            return false
        }
        return true
    }
}
