import SwiftUI

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var input: String = ""
    @Published var isStreaming: Bool = false
    @Published var backendOnline: Bool = false
    @Published var agentMode: Bool = true   // Stage 3: tools on by default
    @Published var lastToolSummary: String = ""
    @Published var lastForgedSkill: String?

    let voice = VoiceController()
    var sessionId: String?
    var onTurn: (() -> Void)?

    func forgeSkillFromChat() async {
        guard let sid = sessionId else { return }
        do {
            if let skill = try await BackendClient.shared.forgeSkill(sessionId: sid) {
                lastForgedSkill = skill.name
                messages.append(Message(
                    role: .assistant,
                    text: "✨ Forged skill `\(skill.name)`: \(skill.description)"
                ))
            } else {
                messages.append(Message(
                    role: .assistant,
                    text: "✨ Nothing in this chat looks reusable enough to crystallise into a skill yet."
                ))
            }
        } catch {
            messages.append(Message(
                role: .assistant,
                text: "⚠️ Forge failed: \(error.localizedDescription)"
            ))
        }
    }

    func checkHealth() async {
        backendOnline = await BackendClient.shared.health()
    }

    func loadSession(_ id: String) async {
        sessionId = id
        messages = []
        guard let detail = try? await BackendClient.shared.getSession(id: id) else { return }
        agentMode = detail.mode == "agentic"
        messages = detail.history.map { hm in
            Message(
                role: hm.role == "user" ? .user : .assistant,
                text: hm.renderedText
            )
        }
    }

    func toggleRecording() async {
        if voice.state == .listening {
            let final = voice.stopListening()
            input = final
            if !final.isEmpty { await send() }
        } else {
            try? await voice.startListening()
        }
    }

    func send() async {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isStreaming else { return }
        input = ""
        messages.append(Message(role: .user, text: trimmed))
        isStreaming = true
        defer {
            isStreaming = false
            onTurn?()
        }
        if agentMode {
            await runAgentLoop(initialText: trimmed)
        } else {
            await runPlainStream(text: trimmed)
        }
    }

    private func runPlainStream(text: String) async {
        var assistant = Message(role: .assistant, text: "")
        messages.append(assistant)
        let idx = messages.count - 1
        do {
            for try await event in BackendClient.shared.chatStream(text: text, sessionId: sessionId) {
                switch event {
                case .session(let sid):
                    sessionId = sid
                case .chunk(let chunk):
                    assistant.text += chunk
                    messages[idx] = assistant
                case .done(let neuronId, _):
                    assistant.neuronId = neuronId
                    messages[idx] = assistant
                }
            }
            voice.speak(assistant.text)
        } catch {
            assistant.text = "⚠️ \(error.localizedDescription)"
            messages[idx] = assistant
        }
    }

    func sendFeedback(at index: Int, positive: Bool) async {
        guard messages.indices.contains(index) else { return }
        guard let nid = messages[index].neuronId else { return }
        messages[index].feedback = positive ? .positive : .negative
        await BackendClient.shared.feedback(neuronId: nid, positive: positive)
    }

    private func runAgentLoop(initialText: String) async {
        var nextText: String? = initialText
        var nextResults: [ToolResult] = []
        var safety = 8  // hard cap on tool rounds per turn

        while safety > 0 {
            safety -= 1
            do {
                let response = try await BackendClient.shared.agenticChat(
                    sessionId: sessionId, text: nextText, toolResults: nextResults
                )
                sessionId = response.session_id
                if !response.text.isEmpty {
                    messages.append(Message(
                        role: .assistant,
                        text: response.text,
                        neuronId: response.assistant_neuron_id
                    ))
                    voice.speak(response.text)
                }
                if response.tool_calls.isEmpty { return }

                lastToolSummary = response.tool_calls.map(\.humanSummary).joined(separator: "\n---\n")
                var results: [ToolResult] = []
                for call in response.tool_calls {
                    let r = await ToolExecutor.shared.execute(call)
                    results.append(r)
                }
                nextText = nil
                nextResults = results
            } catch {
                messages.append(Message(role: .assistant, text: "⚠️ \(error.localizedDescription)"))
                return
            }
        }
        messages.append(Message(role: .assistant, text: "⚠️ tool loop hit safety limit"))
    }
}

struct ChatView: View {
    @StateObject private var vm = ChatViewModel()
    let initialSessionId: String?
    let onTurn: (() -> Void)?

    init(initialSessionId: String? = nil, onTurn: (() -> Void)? = nil) {
        self.initialSessionId = initialSessionId
        self.onTurn = onTurn
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(Array(vm.messages.enumerated()), id: \.element.id) { idx, msg in
                            MessageBubble(message: msg) { positive in
                                Task { await vm.sendFeedback(at: idx, positive: positive) }
                            }
                            .id(msg.id)
                        }
                        if vm.voice.state == .listening, !vm.voice.transcript.isEmpty {
                            MessageBubble(message: Message(role: .user, text: vm.voice.transcript + " …"))
                                .opacity(0.5)
                        }
                    }
                    .padding()
                }
                .onChange(of: vm.messages.last?.text) { _, _ in
                    if let last = vm.messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }
            Divider()
            inputBar
        }
        .task {
            await vm.checkHealth()
            vm.onTurn = onTurn
            if let id = initialSessionId, id != vm.sessionId {
                await vm.loadSession(id)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text("MIRA").font(.headline)
            Circle()
                .fill(vm.backendOnline ? .green : .red)
                .frame(width: 8, height: 8)
            Text(vm.backendOnline ? "brain online" : "brain offline")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button {
                Task { await vm.forgeSkillFromChat() }
            } label: {
                Image(systemName: "sparkles")
            }
            .buttonStyle(.plain)
            .disabled(vm.sessionId == nil || vm.messages.count < 2)
            .help("Forge a reusable skill from this conversation")
            Toggle("⚙︎", isOn: $vm.agentMode)
                .toggleStyle(.button)
                .help("Allow MIRA to use tools (AppleScript, shell, etc.)")
            Toggle("🔊", isOn: $vm.voice.speakResponses)
                .toggleStyle(.button)
                .help("Speak assistant replies")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private var inputBar: some View {
        HStack(spacing: 8) {
            Button {
                Task { await vm.toggleRecording() }
            } label: {
                Image(systemName: vm.voice.state == .listening ? "stop.circle.fill" : "mic.circle.fill")
                    .font(.title2)
                    .foregroundStyle(vm.voice.state == .listening ? .red : .accentColor)
                    .symbolEffect(.pulse, isActive: vm.voice.state == .listening)
            }
            .buttonStyle(.plain)
            .help("Push-to-talk")

            TextField("Ask MIRA…", text: $vm.input, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...5)
                .onSubmit { Task { await vm.send() } }

            Button {
                Task { await vm.send() }
            } label: {
                Image(systemName: "arrow.up.circle.fill").font(.title2)
            }
            .buttonStyle(.plain)
            .disabled(vm.isStreaming || vm.input.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding(10)
    }
}

private struct MessageBubble: View {
    let message: Message
    var onFeedback: ((Bool) -> Void)? = nil

    var body: some View {
        HStack(alignment: .top) {
            if message.role == .user { Spacer(minLength: 40) }
            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                Text(message.text.isEmpty ? "…" : message.text)
                    .textSelection(.enabled)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(
                        RoundedRectangle(cornerRadius: 12)
                            .fill(message.role == .user
                                  ? Color.accentColor.opacity(0.2)
                                  : Color.secondary.opacity(0.12))
                    )
                if message.role == .assistant, message.neuronId != nil {
                    feedbackBar
                }
            }
            if message.role == .assistant { Spacer(minLength: 40) }
        }
    }

    @ViewBuilder
    private var feedbackBar: some View {
        HStack(spacing: 12) {
            Button {
                onFeedback?(true)
            } label: {
                Image(systemName: message.feedback == .positive ? "hand.thumbsup.fill" : "hand.thumbsup")
                    .foregroundStyle(message.feedback == .positive ? Color.green : Color.secondary)
            }
            .buttonStyle(.plain)
            Button {
                onFeedback?(false)
            } label: {
                Image(systemName: message.feedback == .negative ? "hand.thumbsdown.fill" : "hand.thumbsdown")
                    .foregroundStyle(message.feedback == .negative ? Color.red : Color.secondary)
            }
            .buttonStyle(.plain)
        }
        .font(.caption)
        .padding(.leading, 6)
    }
}
