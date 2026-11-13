import Foundation
@testable import SimvltaneaKit

final class SelectionTests: XCTestCase {
    func candidate(_ id: String, _ seconds: Double, favorite: Bool = false, day: Double = 0) -> PhotoCandidate {
        PhotoCandidate(localIdentifier: id, duration: seconds, pixelWidth: 1080, pixelHeight: 1920,
                       created: Date(timeIntervalSince1970: 1_700_000_000 + day * 86_400), isFavorite: favorite)
    }

    func testDurationBoundsFavouritesAndLibraryLimitsApply() {
        let pool = [candidate("short", 0.4), candidate("ok", 5), candidate("long", 45), candidate("fav", 8, favorite: true)]
        var criteria = PhotoCriteria()
        XCTAssertEqual(ExportPlanner.select(pool, criteria: criteria, index: PhotosIndex()).map(\.localIdentifier), ["fav", "ok"])
        criteria.favoritesOnly = true
        XCTAssertEqual(ExportPlanner.select(pool, criteria: criteria, index: PhotosIndex()).map(\.localIdentifier), ["fav"])
        criteria = PhotoCriteria(); criteria.maxSeconds = 10_000
        XCTAssertFalse(ExportPlanner.select([candidate("huge", 700)], criteria: criteria, index: PhotosIndex()).contains { $0.localIdentifier == "huge" })
    }

    func testNewestFirstWithAStableTieBreakAndALimit() {
        let pool = [candidate("b", 3, day: 1), candidate("a", 3, day: 1), candidate("c", 3, day: 9)]
        var criteria = PhotoCriteria()
        XCTAssertEqual(ExportPlanner.select(pool, criteria: criteria, index: PhotosIndex()).map(\.localIdentifier), ["c", "a", "b"])
        criteria.limit = 2
        XCTAssertEqual(ExportPlanner.select(pool.reversed(), criteria: criteria, index: PhotosIndex()).map(\.localIdentifier), ["c", "a"])
        criteria.limit = 0
        XCTAssertTrue(ExportPlanner.select(pool, criteria: criteria, index: PhotosIndex()).isEmpty)
    }

    func testAlreadyImportedAndRefusedVideosAreNotPlannedAgain() throws {
        var index = PhotosIndex()
        index.imported["done"] = "aaaaaaaaaaaa"; index.skipped["bad"] = "export failed"
        let plan = ExportPlanner.select([candidate("done", 3), candidate("bad", 3), candidate("new", 3)], criteria: PhotoCriteria(), index: index)
        XCTAssertEqual(plan.map(\.localIdentifier), ["new"])
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("simv-index-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: url) }
        try index.save(to: url)
        XCTAssertEqual(PhotosIndex.load(from: url), index)
        XCTAssertEqual(PhotosIndex.load(from: url.appendingPathExtension("missing")), PhotosIndex())
    }
}
