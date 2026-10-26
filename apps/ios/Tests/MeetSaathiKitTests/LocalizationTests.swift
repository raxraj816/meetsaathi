import Foundation
import Testing
@testable import MeetSaathiKit

@Suite struct LocalizationTests {
    @Test func keysResolveToEnglishCopyNeverRawKeys() {
        #expect(L("truth_recording") == "Recording")
        #expect(CaptureTruth.paused.label == "Paused · microphone released")
        #expect(L("gap_after", "0:06") == "Audio was unavailable after 0:06; the end time is unknown.")
        #expect(L("you_usage_line", 1.5, 10.0, 3, 200).contains("1.5 of 10 hours · AI requests: 3 of 200"))
    }

    @Test func pluralsChooseOneOrOther() {
        #expect(LP("toast_kept", 1) == "Kept 1 item.")
        #expect(LP("toast_kept", 3) == "Kept 3 items.")
        #expect(LP("days", 7) == "7 days")
    }

    @Test func serverInstantsRenderInTheReadersZone() {
        let ist = TimeZone(identifier: "Asia/Kolkata")!
        let us = Locale(identifier: "en_US")
        // 22:22 UTC on the 18th is already the 19th in India: the date follows the reader, not the server.
        #expect(Dates.date("2026-10-18T22:22:05.123456+00:00", zone: ist, locale: us) == "Oct 19, 2026")
        #expect(Dates.dateTime("2026-10-18T22:22:05Z", zone: ist, locale: us)?.contains("3:52") == true)
        #expect(Dates.date("2026-10-18", zone: ist, locale: us) == "Oct 18, 2026")
        #expect(Dates.date(nil) == nil)
    }
}
