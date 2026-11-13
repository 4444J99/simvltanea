// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "simvltanea-mac",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "SimvltaneaKit", targets: ["SimvltaneaKit"]),
        .executable(name: "simvltanea-mac", targets: ["SimvltaneaMac"]),
        .executable(name: "simv-library", targets: ["SimvLibrary"]),
        .executable(name: "simv-tests", targets: ["SimvTests"]),
    ],
    targets: [
        .target(name: "SimvltaneaKit", path: "sources/kit"),
        .executableTarget(name: "SimvltaneaMac", dependencies: ["SimvltaneaKit"], path: "sources/app"),
        .executableTarget(name: "SimvLibrary", dependencies: ["SimvltaneaKit"], path: "sources/tool"),
        // The Command Line Tools ship no XCTest, so the suite is a self-contained executable: `swift run simv-tests`.
        .executableTarget(name: "SimvTests", dependencies: ["SimvltaneaKit"], path: "tests/kit"),
    ]
)
