import AppKit
import Foundation

/// On launch, if the local brain isn't reachable, guide the user to set it up
/// with the one-line installer. Keeps the downloadable .app path coherent:
/// the GUI alone can't function without the brain, so we make fixing it a
/// two-click affair instead of a silent failure.
@MainActor
enum BrainBootstrap {
    static let installCommand =
        "curl -fsSL https://raw.githubusercontent.com/railers1991-jpg/mira/main/install.sh | bash"

    /// Polls health a few times (the launchd agent may still be starting),
    /// then offers setup if still offline.
    static func checkAndOfferSetup() async {
        for attempt in 0..<5 {
            if await BackendClient.shared.health() { return }
            if attempt < 4 { try? await Task.sleep(nanoseconds: 1_000_000_000) }
        }
        presentSetupAlert()
    }

    private static func presentSetupAlert() {
        let alert = NSAlert()
        alert.messageText = "MIRA's brain isn't running yet"
        alert.informativeText = """
        The chat, memory, voice tools and skills are powered by a small local \
        service. Run this one-line installer in Terminal to set it up (it also \
        registers it to start at login):

        \(installCommand)
        """
        alert.alertStyle = .informational
        alert.addButton(withTitle: "Copy command")
        alert.addButton(withTitle: "Open Terminal")
        alert.addButton(withTitle: "Later")

        switch alert.runModal() {
        case .alertFirstButtonReturn:
            copyCommand()
        case .alertSecondButtonReturn:
            copyCommand()
            NSWorkspace.shared.open(URL(fileURLWithPath: "/System/Applications/Utilities/Terminal.app"))
        default:
            break
        }
    }

    private static func copyCommand() {
        let pb = NSPasteboard.general
        pb.clearContents()
        pb.setString(installCommand, forType: .string)
    }
}
