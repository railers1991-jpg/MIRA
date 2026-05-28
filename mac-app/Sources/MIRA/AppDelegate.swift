import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var panel: NSPanel?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "✦ MIRA"
            button.action = #selector(togglePanel)
            button.target = self
        }
    }

    @objc private func togglePanel() {
        if let panel, panel.isVisible {
            panel.orderOut(nil)
            return
        }
        if panel == nil {
            panel = makePanel()
        }
        panel?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func makePanel() -> NSPanel {
        let view = ChatView()
            .frame(minWidth: 480, minHeight: 600)
        let hosting = NSHostingController(rootView: view)
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 480, height: 600),
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
