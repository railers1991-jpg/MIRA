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
        let assistant_neuron_id: String?
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

    enum StreamEvent {
        case session(String)
        case chunk(String)
        case done(neuronId: String?, modelUsed: String?)
    }

    /// Streaming chat (no tools). Yields JSON-encoded SSE events until done.
    func chatStream(text: String, sessionId: String?) -> AsyncThrowingStream<StreamEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                do {
                    var req = URLRequest(url: base.appendingPathComponent("chat"))
                    req.httpMethod = "POST"
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    var body: [String: Any] = ["text": text, "stream": true]
                    if let sessionId { body["session_id"] = sessionId }
                    req.httpBody = try JSONSerialization.data(withJSONObject: body)
                    let (bytes, response) = try await session.bytes(for: req)
                    guard let http = response as? HTTPURLResponse,
                          (200..<300).contains(http.statusCode) else {
                        throw URLError(.badServerResponse)
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let payload = String(line.dropFirst(6))
                        guard let data = payload.data(using: .utf8),
                              let obj = try? JSONSerialization.jsonObject(with: data)
                                as? [String: Any] else { continue }
                        if let chunk = obj["chunk"] as? String {
                            continuation.yield(.chunk(chunk))
                        } else if let sid = obj["session_id"] as? String {
                            continuation.yield(.session(sid))
                        } else if obj["done"] as? Bool == true {
                            continuation.yield(.done(
                                neuronId: obj["neuron_id"] as? String,
                                modelUsed: obj["model_used"] as? String
                            ))
                            break
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    /// Send ±1 feedback for a stored neuron. Fire-and-forget; errors logged.
    func feedback(neuronId: String, positive: Bool) async {
        var req = URLRequest(url: base.appendingPathComponent("memory/\(neuronId)/feedback"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["signal": positive ? "positive" : "negative"]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        _ = try? await session.data(for: req)
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
