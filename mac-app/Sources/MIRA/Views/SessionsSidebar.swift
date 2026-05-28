import SwiftUI

@MainActor
final class SessionsViewModel: ObservableObject {
    @Published var sessions: [SessionSummary] = []
    @Published var isLoading: Bool = false

    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            sessions = try await BackendClient.shared.listSessions(limit: 100)
        } catch {
            sessions = []
        }
    }

    func delete(_ id: String) async {
        await BackendClient.shared.deleteSession(id: id)
        await refresh()
    }
}

struct SessionsSidebar: View {
    @ObservedObject var vm: SessionsViewModel
    @Binding var selection: String?
    var onNew: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Chats").font(.headline)
                Spacer()
                Button(action: onNew) {
                    Image(systemName: "square.and.pencil")
                }
                .buttonStyle(.plain)
                .help("New chat")
                Button {
                    Task { await vm.refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("Refresh")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            Divider()
            List(selection: $selection) {
                ForEach(vm.sessions) { s in
                    SessionRow(session: s)
                        .tag(s.id)
                        .contextMenu {
                            Button("Delete", role: .destructive) {
                                Task { await vm.delete(s.id) }
                            }
                        }
                }
            }
            .listStyle(.sidebar)
        }
        .task { await vm.refresh() }
    }
}

private struct SessionRow: View {
    let session: SessionSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                if session.mode == "agentic" {
                    Image(systemName: "wrench.and.screwdriver.fill")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Text(session.displayTitle)
                    .lineLimit(1)
            }
            Text(session.updatedAt, format: .relative(presentation: .named))
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 2)
    }
}
