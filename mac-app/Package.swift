// swift-tools-version: 6.0
import PackageDescription

// Tools version 6.0 is required so the manifest links against the modern
// PackageDescription (Swift 6 toolchains dropped the old init symbol). The
// app relies on @MainActor/actor patterns written for Swift 5 semantics, so
// each target pins the Swift 5 language mode to avoid Swift 6 strict-
// concurrency rejections.
let swift5: [SwiftSetting] = [.swiftLanguageMode(.v5)]

let package = Package(
    name: "MIRA",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "MIRA", targets: ["MIRA"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "MIRA",
            path: "Sources/MIRA",
            resources: [
                .copy("Info.plist")
            ],
            swiftSettings: swift5
        ),
        .testTarget(
            name: "MIRATests",
            dependencies: ["MIRA"],
            path: "Tests/MIRATests",
            swiftSettings: swift5
        )
    ]
)
