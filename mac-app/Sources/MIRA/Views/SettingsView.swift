import AppKit
import SwiftUI

struct SettingsView: View {
    @AppStorage("backendURL") private var backendURL: String = "http://127.0.0.1:7842"
    @AppStorage("voiceLocale") private var voiceLocale: String = "ru-RU"
    @AppStorage("wakeWordEnabled") private var wakeWordEnabled: Bool = false

    var body: some View {
        TabView {
            backendTab.tabItem { Label("Backend", systemImage: "brain") }
            voiceTab.tabItem { Label("Voice", systemImage: "waveform") }
            toolsTab.tabItem { Label("Tools", systemImage: "wrench.and.screwdriver") }
            aboutTab.tabItem { Label("About", systemImage: "info.circle") }
        }
        .padding()
        .frame(width: 480, height: 320)
    }

    private var backendTab: some View {
        Form {
            TextField("Brain URL", text: $backendURL)
            Text("Brain runs locally on \(backendURL). Edit and restart MIRA to apply.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private var voiceTab: some View {
        Form {
            Picker("Recognition language", selection: $voiceLocale) {
                Text("Русский").tag("ru-RU")
                Text("English (US)").tag("en-US")
                Text("English (UK)").tag("en-GB")
            }
            Toggle("Listen for wake word (\"Мира\" / \"MIRA\")", isOn: $wakeWordEnabled)
                .onChange(of: wakeWordEnabled) { _, newValue in
                    (NSApp.delegate as? AppDelegate)?.setWakeWordEnabled(newValue)
                }
            Text("Push-to-talk: tap the mic in the chat panel, or press ⌥⇧Space to summon MIRA.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }

    private var toolsTab: some View {
        ToolsSettings()
    }

    private var aboutTab: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("MIRA").font(.title2.bold())
            Text("Memory-Integrated Reasoning Assistant").font(.callout)
            Text("Stage 3: tools (AppleScript, shell, notifications, …)")
                .font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 6)
    }
}

@MainActor
private struct ToolsSettings: View {
    @State private var granted: Set<String> = ConsentManager.shared.grantedKinds()

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Granted tool permissions")
                .font(.headline)
            if granted.isEmpty {
                Text("No tools have been granted blanket permission yet. MIRA asks the first time each tool is used.")
                    .font(.callout).foregroundStyle(.secondary)
            } else {
                ForEach(Array(granted).sorted(), id: \.self) { name in
                    HStack {
                        Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                        Text(name).font(.system(.body, design: .monospaced))
                        Spacer()
                    }
                }
            }
            Spacer()
            HStack {
                Spacer()
                Button("Revoke all", role: .destructive) {
                    ConsentManager.shared.revokeAll()
                    granted = []
                }
            }
            Text("Note: `shell` always asks for confirmation — there is no blanket grant.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}
