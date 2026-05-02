// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "CognitiveIOAuditHelper",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "com.cognitiveio.audit-helper",
            path: "Sources",
            linkerSettings: [
                .linkedFramework("CryptoKit"),
                .linkedFramework("IOKit"),
                .linkedFramework("AppKit"),
            ]
        ),
    ]
)
