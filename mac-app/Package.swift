// swift-tools-version: 6.0
import PackageDescription

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
            ]
        ),
        .testTarget(
            name: "MIRATests",
            dependencies: ["MIRA"],
            path: "Tests/MIRATests"
        )
    ],
    // Keep Swift 5 semantics: the app relies on @MainActor/actor patterns
    // that Swift 6's strict concurrency would otherwise reject. The 6.0
    // tools version is required so the manifest links against the modern
    // PackageDescription (Swift 6 toolchains dropped the old init symbol).
    swiftLanguageModes: [.v5]
)
