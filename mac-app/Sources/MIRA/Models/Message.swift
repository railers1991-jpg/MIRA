import Foundation

struct Message: Identifiable, Equatable {
    enum Role { case user, assistant }
    let id = UUID()
    let role: Role
    var text: String
    var neuronId: String? = nil
    var feedback: Feedback = .none
    let createdAt = Date()

    enum Feedback { case none, positive, negative }
}
