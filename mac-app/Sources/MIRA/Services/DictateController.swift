import AppKit
import Combine
import Foundation
import SwiftUI

/// "Dictate Anywhere" — global hotkey toggles a tiny HUD that records on-device
/// speech and types the result into whichever field has keyboard focus. Works
/// inside any macOS app (Notes, Slack, Xcode, Mail, browser).
@MainActor
final class DictateController: NSObject, ObservableObject {
    @Published private(set) var isActive: Bool = false
    @Published private(set) var transcript: String = ""

    private let voice = VoiceController()
    private var cancellables: Set<AnyCancellable> = []
    private var hud: HUDWindow?

    /// Owners can swap the recognition locale from Settings.
    func setLocale(_ identifier: String) {
        voice.locale = Locale(identifier: identifier)
    }

    func toggle() {
        Task { isActive ? await stop() : await start() }
    }

    private func start() async {
        guard !isActive else { return }
        transcript = ""
        let hud = HUDWindow(dictate: self)
        hud.show()
        self.hud = hud

        // Mirror voice transcript into ours so the HUD updates live.
        voice.$transcript
            .receive(on: RunLoop.main)
            .sink { [weak self] t in self?.transcript = t }
            .store(in: &cancellables)

        do {
            try await voice.startListening()
            isActive = true
        } catch {
            cancellables.removeAll()
            hud.hide()
            self.hud = nil
        }
    }

    private func stop() async {
        guard isActive else { return }
        let final = voice.stopListening()
        isActive = false
        cancellables.removeAll()
        hud?.hide()
        hud = nil

        let trimmed = final.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            typeIntoFocusedField(trimmed)
        }
    }

    /// Emit Unicode keystrokes into whatever field has focus right now.
    private func typeIntoFocusedField(_ text: String) {
        guard let source = CGEventSource(stateID: .combinedSessionState) else { return }
        for scalar in text.unicodeScalars {
            let utf16 = Array(String(scalar).utf16)
            for keyDown in [true, false] {
                guard let event = CGEvent(
                    keyboardEventSource: source, virtualKey: 0, keyDown: keyDown
                ) else { continue }
                utf16.withUnsafeBufferPointer { buf in
                    event.keyboardSetUnicodeString(
                        stringLength: buf.count, unicodeString: buf.baseAddress
                    )
                }
                event.post(tap: .cgAnnotatedSessionEventTap)
            }
        }
    }
}

// MARK: - HUD window

@MainActor
private final class HUDWindow {
    private let panel: NSPanel
    private weak var dictate: DictateController?

    init(dictate: DictateController) {
        self.dictate = dictate
        let content = HUDContent(dictate: dictate)
        let host = NSHostingController(rootView: content)
        panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 320, height: 80),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.contentViewController = host
        panel.isFloatingPanel = true
        panel.level = .statusBar
        panel.hasShadow = true
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.ignoresMouseEvents = false
    }

    func show() {
        guard let screen = NSScreen.main else { return }
        let frame = screen.visibleFrame
        let size = panel.frame.size
        let origin = NSPoint(
            x: frame.midX - size.width / 2,
            y: frame.maxY - size.height - 32
        )
        panel.setFrameOrigin(origin)
        panel.orderFrontRegardless()
    }

    func hide() {
        panel.orderOut(nil)
    }
}

private struct HUDContent: View {
    @ObservedObject var dictate: DictateController

    var body: some View {
        VStack(spacing: 6) {
            HStack(spacing: 8) {
                Circle()
                    .fill(.red)
                    .frame(width: 10, height: 10)
                    .opacity(dictate.isActive ? 1 : 0.3)
                Text("Dictating…").font(.subheadline.weight(.medium))
                Spacer()
                Text("⌃⌥V").font(.caption).foregroundStyle(.secondary)
            }
            Text(dictate.transcript.isEmpty ? "Speak — release ⌃⌥V to type." : dictate.transcript)
                .font(.callout)
                .foregroundStyle(.primary)
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(.regularMaterial)
        )
        .padding(4)
    }
}
