import AppKit
import Carbon.HIToolbox
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var panel: NSPanel?
    private let wakeWord = WakeWordListener()
    private let dictate = DictateController()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "✦ MIRA"
            button.action = #selector(togglePanel)
            button.target = self
        }

        // ⌥⇧Space — toggle the chat panel
        HotkeyManager.register(
            keyCode: UInt32(kVK_Space),
            modifiers: UInt32(optionKey | shiftKey)
        ) { [weak self] in
            self?.togglePanel()
        }
        // ⌃⌥V — toggle "Dictate Anywhere"
        HotkeyManager.register(
            keyCode: UInt32(kVK_ANSI_V),
            modifiers: UInt32(controlKey | optionKey)
        ) { [weak self] in
            self?.dictate.toggle()
        }

        wakeWord.onWake = { [weak self] in
            DispatchQueue.main.async {
                if self?.panel?.isVisible != true { self?.togglePanel() }
            }
        }

        // If the local brain isn't up (common right after a GUI-only DMG
        // install), offer the one-line setup.
        Task { await BrainBootstrap.checkAndOfferSetup() }

        // Register as the tool executor so subscription-driven agent mode
        // can run Mac tools through the brain's bridge.
        AgentSocket.shared.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        HotkeyManager.unregisterAll()
        wakeWord.stop()
        AgentSocket.shared.stop()
    }

    @objc private func togglePanel() {
        if let panel, panel.isVisible {
            panel.orderOut(nil)
            return
        }
        if panel == nil { panel = makePanel() }
        panel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func setWakeWordEnabled(_ enabled: Bool) {
        if enabled { wakeWord.start() } else { wakeWord.stop() }
    }

    var isWakeWordEnabled: Bool { wakeWord.isActive }

    private func makePanel() -> NSPanel {
        let view = ContentView()
            .frame(minWidth: 720, minHeight: 600)
        let hosting = NSHostingController(rootView: view)
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 760, height: 600),
            styleMask: [.titled, .closable, .resizable, .fullSizeContentView, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.title = "MIRA"
        panel.contentViewController = hosting
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.titlebarAppearsTransparent = true
        panel.center()
        return panel
    }
}
