import SwiftUI

@MainActor
final class ChatViewModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var input: String = ""
    @Published var isStreaming: Bool = false
    @Published var backendOnline: Bool = false

    func checkHealth() async {
        backendOnline = await BackendClient.shared.health()
    }

    func send() async {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isStreaming else { return }
        input = ""
        messages.append(Message(role: .user, text: trimmed))
        var assistant = Message(role: .assistant, text: "")
        messages.append(assistant)
        let assistantIndex = messages.count - 1
        isStreaming = true
        defer { isStreaming = false }
        do {
            for try await chunk in BackendClient.shared.chatStream(text: trimmed) {
                assistant.text += chunk
                messages[assistantIndex] = assistant
            }
        } catch {
            assistant.text = "⚠️ \(error.localizedDescription)"
            messages[assistantIndex] = assistant
        }
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
        HStack {
            Text("MIRA").font(.headline)
            Circle()
                .fill(vm.backendOnline ? .green : .red)
                .frame(width: 8, height: 8)
            Text(vm.backendOnline ? "brain online" : "brain offline")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private var inputBar: some View {
        HStack(spacing: 8) {
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
