import SwiftUI

struct ContentView: View {
    @StateObject private var sessions = SessionsViewModel()
    @State private var selectedId: String?
    @State private var chatKey = UUID()

    var body: some View {
        NavigationSplitView {
            SessionsSidebar(vm: sessions, selection: $selectedId) {
                selectedId = nil
                chatKey = UUID()  // forces a fresh ChatView
            }
            .frame(minWidth: 220)
        } detail: {
            ChatView(initialSessionId: selectedId, onTurn: {
                Task { await sessions.refresh() }
            })
            .id(selectedId ?? chatKey.uuidString)
        }
    }
}
