import Foundation

// A small XCTest-shaped harness. The Command Line Tools that build this package ship neither
// XCTest nor swift-testing, so assertions record into a list and `main.swift` runs every suite.

nonisolated(unsafe) var recordedFailures: [String] = []
nonisolated(unsafe) var currentTestName = ""
nonisolated(unsafe) var assertionCount = 0

class XCTestCase {
    required init() {}
    func setUpWithError() throws {}
    func tearDown() {}
}

struct UnwrapFailure: Error {}

func fail(_ message: String, _ line: UInt) {
    recordedFailures.append("\(currentTestName) line \(line): \(message)")
}

func XCTAssertTrue(_ value: @autoclosure () throws -> Bool, _ message: @autoclosure () -> String = "", file: StaticString = #filePath, line: UInt = #line) {
    assertionCount += 1
    do { if try !value() { fail("expected true \(message())", line) } } catch { fail("threw \(error)", line) }
}

func XCTAssertFalse(_ value: @autoclosure () throws -> Bool, _ message: @autoclosure () -> String = "", file: StaticString = #filePath, line: UInt = #line) {
    assertionCount += 1
    do { if try value() { fail("expected false \(message())", line) } } catch { fail("threw \(error)", line) }
}

func XCTAssertEqual<T: Equatable>(_ a: @autoclosure () throws -> T, _ b: @autoclosure () throws -> T, _ message: @autoclosure () -> String = "", file: StaticString = #filePath, line: UInt = #line) {
    assertionCount += 1
    do { let (x, y) = (try a(), try b()); if x != y { fail("\(x) is not equal to \(y) \(message())", line) } } catch { fail("threw \(error)", line) }
}

func XCTAssertEqual<T: FloatingPoint>(_ a: @autoclosure () throws -> T, _ b: @autoclosure () throws -> T, accuracy: T, _ message: @autoclosure () -> String = "", file: StaticString = #filePath, line: UInt = #line) {
    assertionCount += 1
    do { let (x, y) = (try a(), try b()); if !(abs(x - y) <= accuracy) { fail("\(x) is not within \(accuracy) of \(y) \(message())", line) } } catch { fail("threw \(error)", line) }
}

func XCTAssertNil(_ value: @autoclosure () throws -> Any?, _ message: @autoclosure () -> String = "", file: StaticString = #filePath, line: UInt = #line) {
    assertionCount += 1
    do { if let found = try value() { fail("expected nil, got \(found) \(message())", line) } } catch { fail("threw \(error)", line) }
}

func XCTAssertNotNil(_ value: @autoclosure () throws -> Any?, _ message: @autoclosure () -> String = "", file: StaticString = #filePath, line: UInt = #line) {
    assertionCount += 1
    do { if try value() == nil { fail("expected a value \(message())", line) } } catch { fail("threw \(error)", line) }
}

func XCTAssertNoThrow<T>(_ expression: @autoclosure () throws -> T, _ message: @autoclosure () -> String = "", file: StaticString = #filePath, line: UInt = #line) {
    assertionCount += 1
    do { _ = try expression() } catch { fail("unexpected \(error) \(message())", line) }
}

func XCTAssertThrowsError<T>(_ expression: @autoclosure () throws -> T, _ message: @autoclosure () -> String = "", file: StaticString = #filePath, line: UInt = #line, _ handler: (Error) -> Void = { _ in }) {
    assertionCount += 1
    do { _ = try expression(); fail("expected an error \(message())", line) } catch { handler(error) }
}

func XCTUnwrap<T>(_ value: @autoclosure () throws -> T?, file: StaticString = #filePath, line: UInt = #line) throws -> T {
    assertionCount += 1
    guard let found = try value() else { fail("expected a value", line); throw UnwrapFailure() }
    return found
}
