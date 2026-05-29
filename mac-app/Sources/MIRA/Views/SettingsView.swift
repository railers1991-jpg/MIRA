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
            SkillsSettings().tabItem { Label("Skills", systemImage: "sparkles") }
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
            Divider()
            ProvidersView()
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
            Divider()
            Text("Dictate Anywhere: ⌃⌥V starts recording from anywhere in macOS; "
                 + "press ⌃⌥V again to stop and have the transcript typed into the focused field.")
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
private struct ProvidersView: View {
    @State private var info: BackendClient.ProvidersInfo?

    private let labels: [(key: String, name: String, detail: String)] = [
        ("cloud", "Anthropic API", "metered key · powers tool-use / agent mode"),
        ("claude_code", "Claude Pro/Max", "via the claude CLI subscription"),
        ("codex", "ChatGPT / Codex", "via the codex CLI subscription"),
        ("local", "Ollama (local)", "fully offline / private"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Reasoning providers").font(.subheadline.bold())
                Spacer()
                if let info {
                    Text("active: \(info.selected)")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
            if let info {
                ForEach(labels, id: \.key) { row in
                    HStack(spacing: 6) {
                        Image(systemName: (info.available[row.key] ?? false)
                              ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle((info.available[row.key] ?? false) ? .green : .secondary)
                        Text(row.name)
                        Text(row.detail).font(.caption2).foregroundStyle(.tertiary)
                        Spacer()
                    }
                }
                Text("Choose with MIRA_PROVIDER (auto · api · subscription · claude_code · codex · local) "
                     + "in ~/.mira/env, then restart the brain.")
                    .font(.caption2).foregroundStyle(.secondary)
            } else {
                Text("Loading provider status…").font(.caption).foregroundStyle(.secondary)
            }
        }
        .task {
            info = try? await BackendClient.shared.providers()
        }
    }
}

@MainActor
private struct SkillsSettings: View {
    @State private var skills: [Skill] = []
    @State private var isLoading: Bool = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Self-forged skills").font(.headline)
                Spacer()
                Button {
                    Task { await refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
            }
            if let error {
                Text(error).font(.caption).foregroundStyle(.red)
            }
            if skills.isEmpty {
                Text("No skills yet. Have a conversation in agent mode that completes a useful task; "
                     + "MIRA can then forge it into a reusable skill from the chat menu.")
                    .font(.callout).foregroundStyle(.secondary)
            } else {
                List(skills) { skill in
                    SkillRow(skill: skill, onDelete: {
                        Task {
                            await BackendClient.shared.deleteSkill(name: skill.name)
                            await refresh()
                        }
                    })
                }
                .listStyle(.inset)
            }
            Spacer()
            Text("Skills auto-expose as `skill__<name>` tools to Claude; "
                 + "MIRA picks them when their when_to_use matches your request.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
        .task { await refresh() }
    }

    private func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            skills = try await BackendClient.shared.listSkills()
            error = nil
        } catch {
            self.error = "Could not load skills: \(error.localizedDescription)"
        }
    }
}

@MainActor
private struct SkillRow: View {
    let skill: Skill
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(skill.name)
                    .font(.system(.body, design: .monospaced))
                    .bold()
                Spacer()
                if skill.totalRuns > 0 {
                    Text("\(skill.success_count)✓ \(skill.failure_count)✗")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Button(role: .destructive, action: onDelete) {
                    Image(systemName: "trash")
                }
                .buttonStyle(.plain)
                .foregroundStyle(.red)
            }
            Text(skill.description).font(.callout).foregroundStyle(.secondary)
            if !skill.lessons.isEmpty {
                Text("Lessons: " + skill.lessons.suffix(3).joined(separator: " · "))
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 4)
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
