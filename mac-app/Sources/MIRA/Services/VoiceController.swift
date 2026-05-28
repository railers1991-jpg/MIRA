import AVFoundation
import Combine
import Foundation
import Speech

/// On-device speech I/O. STT uses Apple's `Speech` framework with partial
/// results; TTS uses `AVSpeechSynthesizer`. Both work offline on Apple
/// Silicon once the user grants Mic + Speech Recognition permissions.
@MainActor
final class VoiceController: NSObject, ObservableObject {
    enum State: Equatable { case idle, listening, denied, error(String) }

    @Published private(set) var state: State = .idle
    @Published private(set) var transcript: String = ""
    @Published var speakResponses: Bool = true
    @Published var locale: Locale = Locale(identifier: "ru-RU")

    private let audioEngine = AVAudioEngine()
    private var recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?

    private let synthesizer = AVSpeechSynthesizer()

    /// Ask for permission. Safe to call multiple times.
    func requestAuthorization() async -> Bool {
        let speech = await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { status in cont.resume(returning: status) }
        }
        guard speech == .authorized else {
            state = .denied
            return false
        }
        let mic = await AVCaptureDevice.requestAccess(for: .audio)
        if !mic { state = .denied }
        return mic
    }

    func startListening() async throws {
        guard state != .listening else { return }
        if !(await requestAuthorization()) { return }

        recognizer = SFSpeechRecognizer(locale: locale)
        guard let recognizer, recognizer.isAvailable else {
            state = .error("recognizer unavailable for \(locale.identifier)")
            return
        }

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        if #available(macOS 13, *) {
            request.requiresOnDeviceRecognition = true
        }
        self.request = request

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buf, _ in
            request.append(buf)
        }
        audioEngine.prepare()
        try audioEngine.start()

        transcript = ""
        state = .listening
        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            Task { @MainActor in
                if let result {
                    self?.transcript = result.bestTranscription.formattedString
                }
                if error != nil || (result?.isFinal ?? false) {
                    self?.stopListening()
                }
            }
        }
    }

    @discardableResult
    func stopListening() -> String {
        guard state == .listening else { return transcript }
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        task?.finish()
        request = nil
        task = nil
        state = .idle
        return transcript
    }

    func speak(_ text: String) {
        guard speakResponses, !text.isEmpty else { return }
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: locale.identifier)
            ?? AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        synthesizer.speak(utterance)
    }

    func stopSpeaking() {
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
    }
}
