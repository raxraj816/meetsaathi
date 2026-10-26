// swift-tools-version:5.10
// MeetSaathiKit: shared iOS client foundation (core contracts, capture/spool/upload, live controller, SwiftUI).
// The iOS app target (App/, generated with XcodeGen from project.yml) depends on this package.
// macOS is listed only so the platform-neutral parts compile and unit-test with `swift test` on CI Macs.
import PackageDescription

let package = Package(
    name: "MeetSaathiKit",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "MeetSaathiKit", targets: ["MeetSaathiKit"])],
    targets: [
        .target(name: "MeetSaathiKit", path: "Sources/MeetSaathiKit"),
        .testTarget(name: "MeetSaathiKitTests", dependencies: ["MeetSaathiKit"], path: "Tests/MeetSaathiKitTests",
                    resources: [.copy("Resources/state_machine_v1.json")]),
    ]
)
