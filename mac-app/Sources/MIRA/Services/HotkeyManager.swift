import Carbon.HIToolbox
import Foundation

/// Registers system-wide hotkeys via Carbon's `RegisterEventHotKey`. Supports
/// multiple distinct bindings; each callback runs on the main queue. Requires
/// the binary to live inside a proper `.app` bundle — Carbon hotkeys don't
/// work for `swift run`.
final class HotkeyManager {
    private struct Registration {
        let ref: EventHotKeyRef
        let callback: () -> Void
    }

    private static let signature: OSType = 0x4D495241  // 'MIRA'
    private static var nextID: UInt32 = 1
    private static var registrations: [UInt32: Registration] = [:]
    private static var handlerInstalled = false

    /// Register a hotkey. Returns its id; pass to `unregister` to remove.
    @discardableResult
    static func register(
        keyCode: UInt32,
        modifiers: UInt32,
        callback: @escaping () -> Void
    ) -> UInt32 {
        installHandlerIfNeeded()
        let id = nextID
        nextID += 1
        var ref: EventHotKeyRef?
        let hotKeyID = EventHotKeyID(signature: signature, id: id)
        let status = RegisterEventHotKey(
            keyCode, modifiers, hotKeyID,
            GetApplicationEventTarget(), 0, &ref
        )
        guard status == noErr, let ref else { return 0 }
        registrations[id] = Registration(ref: ref, callback: callback)
        return id
    }

    static func unregister(_ id: UInt32) {
        if let reg = registrations.removeValue(forKey: id) {
            UnregisterEventHotKey(reg.ref)
        }
    }

    static func unregisterAll() {
        for (_, reg) in registrations { UnregisterEventHotKey(reg.ref) }
        registrations.removeAll()
    }

    private static func installHandlerIfNeeded() {
        guard !handlerInstalled else { return }
        handlerInstalled = true
        var spec = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        InstallEventHandler(GetApplicationEventTarget(), { _, event, _ -> OSStatus in
            var hkID = EventHotKeyID()
            GetEventParameter(
                event, EventParamName(kEventParamDirectObject),
                EventParamType(typeEventHotKeyID), nil,
                MemoryLayout<EventHotKeyID>.size, nil, &hkID
            )
            if hkID.signature == HotkeyManager.signature,
               let callback = HotkeyManager.registrations[hkID.id]?.callback {
                DispatchQueue.main.async(execute: callback)
            }
            return noErr
        }, 1, &spec, nil, nil)
    }
}
