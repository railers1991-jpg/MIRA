import AVFoundation
import Foundation
import Speech

/// Always-on background listener for the wake word. Uses a separate
/// recognition task from `VoiceController` so the user can toggle between
/// passive (just wake-word) and active (push-to-talk) modes.
///
/// Apple's `SFSpeechRecognizer` rotates tasks every ~1 minute, so we
/// restart on any termination. Trigger fires when the rolling transcript
/// contains one of the wake phrases.
@MainActor
final class WakeWordListener: NSObject, ObservableObject {
    @Published private(set) var isActive: Bool = false
    var onWake: (() -> Void)?

    /// Phrases (lower-cased, accent-insensitive) that fire the wake event.
    var phrases: [String] = ["мира", "mira", "слушай мира", "hey mira"]

    private let engine = AVAudioEngine()
    private var recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var lastFireAt: Date = .distantPast

    func start(locale: Locale = Locale(identifier: "ru-RU")) {
        guard !isActive else { return }
        recognizer = SFSpeechRecognizer(locale: locale)
        guard recognizer?.isAvailable == true else { return }
        startTask()
    }

    func stop() {
        isActive = false
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        task?.cancel()
        request = nil
        task = nil
    }

    private func startTask() {
        guard let recognizer else { return }
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        if #available(macOS 13, *) {
            request.requiresOnDeviceRecognition = true
        }
        self.request = request

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buf, _ in
            request.append(buf)
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            isActive = false
            return
        }
        isActive = true

        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            Task { @MainActor in
                guard let self else { return }
                if let result {
                    self.checkWake(result.bestTranscription.formattedString)
                }
                if error != nil || (result?.isFinal ?? false) {
                    // Restart so the listener stays alive past Apple's per-task limit.
                    self.engine.stop()
                    self.engine.inputNode.removeTap(onBus: 0)
                    if self.isActive { self.startTask() }
                }
            }
        }
    }

    private func checkWake(_ text: String) {
        let normalized = text.lowercased()
        guard phrases.contains(where: { normalized.contains($0) }) else { return }
        // Debounce: avoid firing many times for the same utterance.
        guard Date().timeIntervalSince(lastFireAt) > 1.5 else { return }
        lastFireAt = Date()
        onWake?()
    }
}
