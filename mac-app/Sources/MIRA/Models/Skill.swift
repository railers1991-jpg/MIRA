import Foundation

struct Skill: Identifiable, Decodable, Equatable {
    let name: String
    let description: String
    let when_to_use: String
    let lessons: [String]
    let success_count: Int
    let failure_count: Int
    let created_at: Double
    let last_used_at: Double

    var id: String { name }

    var totalRuns: Int { success_count + failure_count }

    var successRate: Double {
        let total = totalRuns
        return total == 0 ? 0 : Double(success_count) / Double(total)
    }

    var lastUsedAt: Date { Date(timeIntervalSince1970: last_used_at) }
}

struct ForgedSkillResponse: Decodable {
    let created: Skill?
}
