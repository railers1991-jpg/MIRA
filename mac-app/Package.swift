// swift-tools-version: 6.0
import PackageDescription

// Tools version 6.0 is required so the manifest links on Swift 6 toolchains
// (the old PackageDescription init symbol was dropped). The Swift 5 language
// mode is forced at build time via build-app.sh (-Xswiftc -swift-version 5),
// because the in-manifest language-mode APIs aren't exposed at
// package-description 6.0 on this toolchain.
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
    ]
)
