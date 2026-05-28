import Foundation

struct ToolCall: Identifiable, Codable, Equatable {
    let id: String
    let name: String
    let input: JSONValue

    var humanSummary: String {
        switch name {
        case "run_applescript":
            return "Run AppleScript:\n\n" + (input.dict?["script"]?.string ?? "—")
        case "shell":
            return "Run shell command:\n\n" + (input.dict?["command"]?.string ?? "—")
        case "open_url":
            return "Open URL: " + (input.dict?["url"]?.string ?? "—")
        case "notify":
            return "Show notification: " + (input.dict?["title"]?.string ?? "—")
        case "get_active_app":
            return "Read the frontmost app"
        case "read_screen":
            return "Capture the screen and send it to MIRA"
        case "read_clipboard":
            return "Read the clipboard"
        case "write_clipboard":
            return "Write to clipboard:\n\n" + (input.dict?["text"]?.string ?? "—")
        case "read_file":
            return "Read file: " + (input.dict?["path"]?.string ?? "—")
        case "type_text":
            return "Type text:\n\n" + (input.dict?["text"]?.string ?? "—")
        default:
            return "Run tool: \(name)"
        }
    }
}

struct ToolResult: Codable, Equatable {
    let id: String
    let output: String
    /// Optional base64-encoded PNG. When present, the brain attaches it as
    /// an image content block in the tool_result so the model can see it.
    var image_b64: String?

    init(id: String, output: String, image_b64: String? = nil) {
        self.id = id
        self.output = output
        self.image_b64 = image_b64
    }
}

/// Minimal JSON value that round-trips through Codable. Used for arbitrary
/// tool input dictionaries.
enum JSONValue: Codable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case null
    case array([JSONValue])
    case object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null; return }
        if let v = try? c.decode(Bool.self) { self = .bool(v); return }
        if let v = try? c.decode(Double.self) { self = .number(v); return }
        if let v = try? c.decode(String.self) { self = .string(v); return }
        if let v = try? c.decode([JSONValue].self) { self = .array(v); return }
        if let v = try? c.decode([String: JSONValue].self) { self = .object(v); return }
        throw DecodingError.dataCorruptedError(in: c, debugDescription: "unsupported JSON value")
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        }
    }

    var string: String? { if case .string(let s) = self { return s } else { return nil } }
    var dict: [String: JSONValue]? { if case .object(let d) = self { return d } else { return nil } }
    var number: Double? { if case .number(let n) = self { return n } else { return nil } }
}
