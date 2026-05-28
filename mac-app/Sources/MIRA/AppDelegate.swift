import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var panel: NSPanel?
    private let hotkey = HotkeyManager()
    private let wakeWord = WakeWordListener()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "✦ MIRA"
            button.action = #selector(togglePanel)
            button.target = self
        }

        hotkey.onFire = { [weak self] in self?.togglePanel() }
        hotkey.register()  // ⌥⇧Space

        // Wake-word is opt-in; off by default. The Settings pane will
        // expose a toggle once Stage 2 ships in user-facing form.
        wakeWord.onWake = { [weak self] in
            DispatchQueue.main.async {
                if self?.panel?.isVisible != true { self?.togglePanel() }
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        hotkey.unregister()
        wakeWord.stop()
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
