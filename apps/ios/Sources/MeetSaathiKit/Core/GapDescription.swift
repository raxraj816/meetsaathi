import Foundation

/// Unknown ends stay unknown; adjacent source timestamps only bound an upload gap approximately.
public func captureGapDescription(startMs: Int64?, endMs: Int64?, estimated: Bool, reason: String) -> String {
    guard let startMs, startMs >= 0, endMs == nil || endMs! >= startMs else {
        return L("gap_timing_unknown")
    }
    let start = gapClock(startMs)
    guard let endMs else { return L("gap_after", start) }
    let end = gapClock(endMs)
    return L(estimated || reason == "UPLOAD_MISSING" ? "gap_between_approx" : "gap_between", start, end)
}

extension Gap {
    public var description: String {
        captureGapDescription(startMs: startMs, endMs: endMs, estimated: timeBoundsEstimated == true, reason: reason)
    }
}

private func gapClock(_ ms: Int64) -> String {
    let total = ms / 1000
    let minutes = (total % 3600) / 60
    let seconds = total % 60
    let tail = String(format: "%02lld:%02lld", minutes, seconds)
    return total >= 3600 ? "\(total / 3600):\(tail)" : "\(minutes):" + String(format: "%02lld", seconds)
}
