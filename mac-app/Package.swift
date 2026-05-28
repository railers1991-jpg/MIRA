// swift-tools-version:5.9
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
            path: "Sources/MIRA"
        ),
        .testTarget(
            name: "MIRATests",
            dependencies: ["MIRA"],
            path: "Tests/MIRATests"
        )
    ]
)
