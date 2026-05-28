import Foundation

struct Message: Identifiable, Equatable {
    enum Role { case user, assistant }
    let id = UUID()
    let role: Role
    var text: String
    let createdAt = Date()
}
