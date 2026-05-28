import AppKit
import Foundation
import ScreenCaptureKit

/// Captures the main display as a PNG using ScreenCaptureKit. Requires the
/// user to grant Screen Recording in System Settings → Privacy & Security.
@available(macOS 14, *)
enum ScreenCapture {
    enum CaptureError: Error {
        case noDisplay
        case captureFailed(String)
        case encodingFailed
    }

    static func capturePNG(scale: CGFloat = 1.0) async throws -> Data {
        let content = try await SCShareableContent.current
        guard let display = content.displays.first else { throw CaptureError.noDisplay }

        let filter = SCContentFilter(display: display, excludingWindows: [])
        let config = SCStreamConfiguration()
        config.width = Int(CGFloat(display.width) * scale)
        config.height = Int(CGFloat(display.height) * scale)
        config.showsCursor = false

        let cgImage: CGImage
        do {
            cgImage = try await SCScreenshotManager.captureImage(
                contentFilter: filter, configuration: config
            )
        } catch {
            throw CaptureError.captureFailed(error.localizedDescription)
        }

        let bitmap = NSBitmapImageRep(cgImage: cgImage)
        guard let png = bitmap.representation(using: .png, properties: [:]) else {
            throw CaptureError.encodingFailed
        }
        return png
    }
}
