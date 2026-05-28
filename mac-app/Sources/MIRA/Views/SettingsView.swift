import AppKit
import SwiftUI

struct SettingsView: View {
    @AppStorage("backendURL") private var backendURL: String = "http://127.0.0.1:7842"
    @AppStorage("voiceLocale") private var voiceLocale: String = "ru-RU"
    @AppStorage("wakeWordEnabled") private var wakeWordEnabled: Bool = false

    var body: some View {
        TabView {
            backendTab
                .tabItem { Label("Backend", systemImage: "brain") }
            voiceTab
                .tabItem { Label("Voice", systemImage: "waveform") }
            aboutTab
                .tabItem { Label("About", systemImage: "info.circle") }
        }
        .padding()
        .frame(width: 460, height: 280)
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

    private var aboutTab: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("MIRA").font(.title2.bold())
            Text("Memory-Integrated Reasoning Assistant").font(.callout)
            Text("Stage 2: voice (STT + TTS + wake word)")
                .font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.top, 6)
    }
}
