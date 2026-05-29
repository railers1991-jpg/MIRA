import AppKit
import Foundation

/// First-time consent for each tool kind. Persisted in UserDefaults so the
/// user only sees the dialog once per tool, except for `shell` which always
/// asks — too powerful to grant blanket consent.
@MainActor
final class ConsentManager {
    static let shared = ConsentManager()

    private static let defaultsKey = "mira.consents.v1"
    private let alwaysAskTools: Set<String> = ["shell"]

    func grantedKinds() -> Set<String> {
        Set(UserDefaults.standard.stringArray(forKey: Self.defaultsKey) ?? [])
    }

    func isGranted(_ tool: String) -> Bool {
        !alwaysAskTools.contains(tool) && grantedKinds().contains(tool)
    }

    /// Returns true if the user approved this tool call. May prompt.
    func askIfNeeded(for call: ToolCall) -> Bool {
        if isGranted(call.name) { return true }

        let alert = NSAlert()
        alert.messageText = "MIRA wants to use “\(call.name)”"
        alert.informativeText = call.humanSummary
        alert.alertStyle = alwaysAskTools.contains(call.name) ? .critical : .warning
        alert.addButton(withTitle: "Allow")
        alert.addButton(withTitle: "Deny")
        if !alwaysAskTools.contains(call.name) {
            alert.addButton(withTitle: "Always allow")
        }

        let response = alert.runModal()
        switch response {
        case .alertFirstButtonReturn:
            return true
        case .alertSecondButtonReturn:
            return false
        case .alertThirdButtonReturn:
            var granted = grantedKinds()
            granted.insert(call.name)
            UserDefaults.standard.set(Array(granted), forKey: Self.defaultsKey)
            return true
        default:
            return false
        }
    }

    func revokeAll() {
        UserDefaults.standard.removeObject(forKey: Self.defaultsKey)
    }
}
