import Foundation

struct SessionSummary: Identifiable, Decodable, Equatable, Hashable {
    let id: String
    let title: String?
    let mode: String
    let created_at: Double
    let updated_at: Double
    let history_bytes: Int

    var displayTitle: String {
        title?.isEmpty == false ? title! : defaultTitle
    }

    private var defaultTitle: String {
        mode == "agentic" ? "Agentic chat" : "New chat"
    }

    var updatedAt: Date { Date(timeIntervalSince1970: updated_at) }
}

struct SessionDetail: Decodable {
    let id: String
    let title: String?
    let mode: String
    let history: [HistoryMessage]
    let created_at: Double
    let updated_at: Double
}

/// Decodes Anthropic-shaped history rows. Either `content` is a plain string
/// (plain chat) or a list of content blocks (agentic) — we only render the
/// human-readable text bits.
struct HistoryMessage: Decodable {
    let role: String
    let content: ContentValue

    enum ContentValue: Decodable {
        case text(String)
        case blocks([Block])

        init(from decoder: Decoder) throws {
            let c = try decoder.singleValueContainer()
            if let s = try? c.decode(String.self) {
                self = .text(s)
            } else if let blocks = try? c.decode([Block].self) {
                self = .blocks(blocks)
            } else {
                self = .text("")
            }
        }
    }

    struct Block: Decodable {
        let type: String
        let text: String?
    }

    /// Plain-text rendering for the chat bubble. Tool calls become a faint stub.
    var renderedText: String {
        switch content {
        case .text(let s): return s
        case .blocks(let blocks):
            return blocks.compactMap { block -> String? in
                if block.type == "text" { return block.text }
                if block.type == "tool_use" { return "🛠 (tool call)" }
                if block.type == "tool_result" { return nil }
                return nil
            }.joined(separator: "\n")
        }
    }
}
