import Foundation

/// Keeps a WebSocket open to the brain's /ws/agent so the Mac can act as the
/// tool executor when a subscription CLI drives agent mode. The brain pushes
/// `{type:"tool_call", id, name, input}`; we run it through ToolExecutor (with
/// the usual consent) and reply `{type:"tool_result", id, output, image_b64}`.
///
/// Auto-reconnects with backoff so it survives brain restarts.
@MainActor
final class AgentSocket: NSObject {
    static let shared = AgentSocket()

    private var task: URLSessionWebSocketTask?
    private var session: URLSession!
    private var url: URL
    private var running = false
    private var backoff: UInt64 = 1

    init(base: URL = URL(string: "ws://127.0.0.1:7842")!) {
        self.url = base.appendingPathComponent("ws/agent")
        super.init()
        self.session = URLSession(configuration: .default)
    }

    func start() {
        guard !running else { return }
        running = true
        connect()
    }

    func stop() {
        running = false
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
    }

    private func connect() {
        guard running else { return }
        let task = session.webSocketTask(with: url)
        self.task = task
        task.resume()
        receiveLoop()
    }

    private func scheduleReconnect() {
        guard running else { return }
        let delay = backoff
        backoff = min(backoff * 2, 30)
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: delay * 1_000_000_000)
            self?.connect()
        }
    }

    private func receiveLoop() {
        task?.receive { [weak self] result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .failure:
                    self.task = nil
                    self.scheduleReconnect()
                case .success(let message):
                    self.backoff = 1
                    await self.handle(message)
                    self.receiveLoop()
                }
            }
        }
    }

    private func handle(_ message: URLSessionWebSocketTask.Message) async {
        let data: Data?
        switch message {
        case .string(let s): data = s.data(using: .utf8)
        case .data(let d): data = d
        @unknown default: data = nil
        }
        guard let data,
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              obj["type"] as? String == "tool_call",
              let id = obj["id"] as? String,
              let name = obj["name"] as? String else { return }

        let input = obj["input"] as? [String: Any] ?? [:]
        let call = decodeCall(id: id, name: name, input: input)
        let result = await ToolExecutor.shared.execute(call)
        await send(result)
    }

    private func decodeCall(id: String, name: String, input: [String: Any]) -> ToolCall {
        let data = (try? JSONSerialization.data(withJSONObject: input)) ?? Data("{}".utf8)
        let value = (try? JSONDecoder().decode(JSONValue.self, from: data)) ?? .object([:])
        return ToolCall(id: id, name: name, input: value)
    }

    private func send(_ result: ToolResult) async {
        var payload: [String: Any] = [
            "type": "tool_result",
            "id": result.id,
            "output": result.output,
        ]
        if let img = result.image_b64 { payload["image_b64"] = img }
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let text = String(data: data, encoding: .utf8) else { return }
        try? await task?.send(.string(text))
    }
}
