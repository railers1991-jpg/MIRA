import SwiftUI

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var input: String = ""
    @Published var isStreaming: Bool = false
    @Published var backendOnline: Bool = false
    @Published var agentMode: Bool = true   // Stage 3: tools on by default
    @Published var lastToolSummary: String = ""

    let voice = VoiceController()
    private var sessionId: String?

    func checkHealth() async {
        backendOnline = await BackendClient.shared.health()
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
        defer { isStreaming = false }
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
            for try await chunk in BackendClient.shared.chatStream(text: text) {
                assistant.text += chunk
                messages[idx] = assistant
            }
            voice.speak(assistant.text)
        } catch {
            assistant.text = "⚠️ \(error.localizedDescription)"
            messages[idx] = assistant
        }
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
                    messages.append(Message(role: .assistant, text: response.text))
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

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(vm.messages) { msg in
                            MessageBubble(message: msg).id(msg.id)
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
        .task { await vm.checkHealth() }
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

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 40) }
            Text(message.text.isEmpty ? "…" : message.text)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 12)
                        .fill(message.role == .user ? Color.accentColor.opacity(0.2) : Color.secondary.opacity(0.12))
                )
            if message.role == .assistant { Spacer(minLength: 40) }
        }
    }
}
