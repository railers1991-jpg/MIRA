import Carbon.HIToolbox
import Foundation

/// Registers a single system-wide hotkey via Carbon's `RegisterEventHotKey`.
/// Default binding: ⌥⇧Space toggles the MIRA panel. The hotkey is
/// consumed (other apps don't see it). Requires the binary to run inside
/// a proper `.app` bundle (Carbon hotkeys won't work for `swift run`).
final class HotkeyManager {
    var onFire: (() -> Void)?

    private var hotKeyRef: EventHotKeyRef?
    private static let signature: OSType = 0x4D495241  // 'MIRA'
    private static let id: UInt32 = 1

    private static var handlerInstalled = false
    private static weak var current: HotkeyManager?

    func register(keyCode: UInt32 = UInt32(kVK_Space),
                  modifiers: UInt32 = UInt32(optionKey | shiftKey)) {
        Self.installHandlerIfNeeded()
        Self.current = self

        var ref: EventHotKeyRef?
        let hotKeyID = EventHotKeyID(signature: Self.signature, id: Self.id)
        let status = RegisterEventHotKey(keyCode, modifiers, hotKeyID,
                                         GetApplicationEventTarget(), 0, &ref)
        if status == noErr { hotKeyRef = ref }
    }

    func unregister() {
        if let hotKeyRef { UnregisterEventHotKey(hotKeyRef) }
        hotKeyRef = nil
    }

    private static func installHandlerIfNeeded() {
        guard !handlerInstalled else { return }
        handlerInstalled = true
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                                 eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, event, _ -> OSStatus in
            var hkID = EventHotKeyID()
            GetEventParameter(event, EventParamName(kEventParamDirectObject),
                              EventParamType(typeEventHotKeyID), nil,
                              MemoryLayout<EventHotKeyID>.size, nil, &hkID)
            if hkID.signature == HotkeyManager.signature, hkID.id == HotkeyManager.id {
                DispatchQueue.main.async { HotkeyManager.current?.onFire?() }
            }
            return noErr
        }, 1, &spec, nil, nil)
    }
}
