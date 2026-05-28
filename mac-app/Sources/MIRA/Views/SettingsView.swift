import SwiftUI

struct SettingsView: View {
    @AppStorage("backendURL") private var backendURL: String = "http://127.0.0.1:7842"

    var body: some View {
        Form {
            Section("Backend") {
                TextField("Brain URL", text: $backendURL)
            }
            Section("About") {
                Text("MIRA · Memory-Integrated Reasoning Assistant").font(.callout)
                Text("Stage 1: chat + hybrid LLM + neuron memory").font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding()
        .frame(width: 420, height: 220)
    }
}
