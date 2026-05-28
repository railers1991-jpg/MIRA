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
        let session_id: String?
        let tool_calls: [ToolCall]
    }

    /// Plain non-agentic chat (no tools). Returns the assistant text.
    func chat(text: String) async throws -> ChatResponse {
        try await postChat(["text": text, "stream": false])
    }

    /// Agentic chat round-trip: send either user text or tool results.
    /// Returns whatever the brain says — may include further tool_calls.
    func agenticChat(
        sessionId: String?,
        text: String?,
        toolResults: [ToolResult]
    ) async throws -> ChatResponse {
        var body: [String: Any] = ["stream": false, "tools_enabled": true]
        if let sessionId { body["session_id"] = sessionId }
        if let text { body["text"] = text }
        if !toolResults.isEmpty {
            body["tool_results"] = toolResults.map { r -> [String: Any] in
                var item: [String: Any] = ["id": r.id, "output": r.output]
                if let img = r.image_b64 { item["image_b64"] = img }
                return item
            }
        }
        return try await postChat(body)
    }

    private func postChat(_ body: [String: Any]) async throws -> ChatResponse {
        var req = URLRequest(url: base.appendingPathComponent("chat"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let msg = String(data: data, encoding: .utf8) ?? "<no body>"
            throw NSError(
                domain: "BackendClient", code: (response as? HTTPURLResponse)?.statusCode ?? -1,
                userInfo: [NSLocalizedDescriptionKey: msg]
            )
        }
        return try JSONDecoder().decode(ChatResponse.self, from: data)
    }

    /// Streaming chat (no tools). Yields text chunks until [DONE].
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
