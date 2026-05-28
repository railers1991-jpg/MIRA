import AppKit
import Foundation
import UserNotifications

/// Executes tool calls returned by the brain. All actions are local;
/// nothing is sent over the network from here. Each call is gated by
/// `ConsentManager`.
@MainActor
final class ToolExecutor {
    static let shared = ToolExecutor()

    func execute(_ call: ToolCall) async -> ToolResult {
        guard ConsentManager.shared.askIfNeeded(for: call) else {
            return ToolResult(id: call.id, output: "ERROR: user denied this tool call")
        }
        switch call.name {
        case "run_applescript":
            return await runAppleScript(call)
        case "shell":
            return await runShell(call)
        case "open_url":
            return openURL(call)
        case "notify":
            return await notify(call)
        case "get_active_app":
            return getActiveApp(call)
        case "read_screen":
            return await readScreen(call)
        default:
            return ToolResult(id: call.id, output: "ERROR: unknown tool \(call.name)")
        }
    }

    private func readScreen(_ call: ToolCall) async -> ToolResult {
        if #available(macOS 14, *) {
            let index = Int(call.input.dict?["display_index"]?.number ?? 0)
            do {
                let png = try await ScreenCapture.capturePNG(displayIndex: index)
                return ToolResult(
                    id: call.id,
                    output: "captured display \(index): \(png.count) bytes",
                    image_b64: png.base64EncodedString()
                )
            } catch {
                return ToolResult(id: call.id, output: "ERROR: \(error)")
            }
        }
        return ToolResult(id: call.id, output: "ERROR: screen capture requires macOS 14+")
    }

    // MARK: - Implementations

    private func runAppleScript(_ call: ToolCall) async -> ToolResult {
        guard let script = call.input.dict?["script"]?.string else {
            return ToolResult(id: call.id, output: "ERROR: missing script")
        }
        return await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                var error: NSDictionary?
                let result = NSAppleScript(source: script)?.executeAndReturnError(&error)
                if let error {
                    cont.resume(returning: ToolResult(
                        id: call.id,
                        output: "ERROR: \(error[NSAppleScript.errorMessage] ?? "applescript failed")"
                    ))
                } else {
                    cont.resume(returning: ToolResult(id: call.id, output: result?.stringValue ?? "ok"))
                }
            }
        }
    }

    private func runShell(_ call: ToolCall) async -> ToolResult {
        guard let command = call.input.dict?["command"]?.string else {
            return ToolResult(id: call.id, output: "ERROR: missing command")
        }
        let timeout = call.input.dict?["timeout_s"]?.number ?? 30
        return await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/bin/zsh")
                process.arguments = ["-lc", command]
                let pipe = Pipe()
                process.standardOutput = pipe
                process.standardError = pipe
                do {
                    try process.run()
                } catch {
                    cont.resume(returning: ToolResult(id: call.id, output: "ERROR: \(error.localizedDescription)"))
                    return
                }
                let deadline = Date().addingTimeInterval(timeout)
                while process.isRunning, Date() < deadline {
                    Thread.sleep(forTimeInterval: 0.05)
                }
                if process.isRunning {
                    process.terminate()
                    cont.resume(returning: ToolResult(id: call.id, output: "ERROR: timeout after \(Int(timeout))s"))
                    return
                }
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                let out = String(data: data, encoding: .utf8) ?? ""
                cont.resume(returning: ToolResult(id: call.id, output: out.isEmpty ? "(no output)" : out))
            }
        }
    }

    private func openURL(_ call: ToolCall) -> ToolResult {
        guard let urlString = call.input.dict?["url"]?.string,
              let url = URL(string: urlString) else {
            return ToolResult(id: call.id, output: "ERROR: invalid url")
        }
        NSWorkspace.shared.open(url)
        return ToolResult(id: call.id, output: "opened \(urlString)")
    }

    private func notify(_ call: ToolCall) async -> ToolResult {
        guard let title = call.input.dict?["title"]?.string,
              let body = call.input.dict?["body"]?.string else {
            return ToolResult(id: call.id, output: "ERROR: missing title or body")
        }
        let center = UNUserNotificationCenter.current()
        let granted = (try? await center.requestAuthorization(options: [.alert, .sound])) ?? false
        guard granted else { return ToolResult(id: call.id, output: "ERROR: notifications not authorized") }

        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        do {
            try await center.add(request)
            return ToolResult(id: call.id, output: "delivered")
        } catch {
            return ToolResult(id: call.id, output: "ERROR: \(error.localizedDescription)")
        }
    }

    private func getActiveApp(_ call: ToolCall) -> ToolResult {
        let app = NSWorkspace.shared.frontmostApplication
        let info: [String: String] = [
            "bundle_id": app?.bundleIdentifier ?? "unknown",
            "name": app?.localizedName ?? "unknown",
            "pid": app.map { String($0.processIdentifier) } ?? "0",
        ]
        let json = (try? JSONSerialization.data(withJSONObject: info)).flatMap { String(data: $0, encoding: .utf8) }
        return ToolResult(id: call.id, output: json ?? "{}")
    }
}
