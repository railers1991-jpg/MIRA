import SwiftUI

@main
struct MIRAApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        // Menu-bar-only app: no main window scene. The chat panel is a
        // floating NSPanel managed by AppDelegate.
        Settings {
            SettingsView()
        }
    }
}
