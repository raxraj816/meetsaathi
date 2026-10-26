import MeetSaathiKit
import SwiftUI

@main
struct MeetSaathiApp: App {
    // Backend base URL comes from the build configuration (Info.plist MSApiBaseURL), never hard-coded per environment.
    @StateObject private var model = AppModel(baseURL: URL(string: Bundle.main.object(forInfoDictionaryKey: "MSApiBaseURL") as? String
                                                           ?? "http://localhost:8080")!)

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .preferredColorScheme(nil) // follows system light/dark
        }
    }
}
