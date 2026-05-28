import XCTest
@testable import MIRA

final class MessageTests: XCTestCase {
    func testRolesDistinct() {
        let user = Message(role: .user, text: "hi")
        let asst = Message(role: .assistant, text: "hello")
        XCTAssertNotEqual(user.id, asst.id)
        XCTAssertEqual(user.role, .user)
        XCTAssertEqual(asst.role, .assistant)
    }
}
