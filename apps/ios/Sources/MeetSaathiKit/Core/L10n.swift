import Foundation

/// Localized UI copy by stable key (shared with Android strings.xml; source: qa/i18n/strings_en.py).
/// Looks up the app bundle's String Catalog first and falls back to the compiled-in English table, so a missing
/// translation never shows a raw key. Arguments use positional printf specifiers (%1$@, %1$d, %1$.1f).
public func L(_ key: String, _ args: CVarArg...) -> String {
    let fallback = L10nEnglish.strings[key] ?? key
    let format = Bundle.main.localizedString(forKey: key, value: fallback, table: nil)
    return args.isEmpty ? format : String(format: format, locale: Locale.current, arguments: args)
}

/// Plural-aware copy (catalog plural variations; English one/other fallback).
public func LP(_ key: String, _ count: Int) -> String {
    let main = Bundle.main.localizedString(forKey: key, value: "\u{0}", table: nil)
    if main != "\u{0}" && main != key { return String.localizedStringWithFormat(main, count) }
    guard let p = L10nEnglish.plurals[key] else { return key }
    return String(format: count == 1 ? p.one : p.other, locale: Locale.current, count)
}

/// Server timestamps are UTC instants; people read them in their own time zone and locale.
public enum Dates {
    private static func instant(_ iso: String) -> Date? {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: iso) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: iso)
    }

    public static func date(_ iso: String?, zone: TimeZone = .current, locale: Locale = .current) -> String? {
        guard let iso, !iso.isEmpty else { return nil }
        let out = DateFormatter()
        out.locale = locale; out.timeZone = zone; out.dateStyle = .medium; out.timeStyle = .none
        if let d = instant(iso) { return out.string(from: d) }
        let day = DateFormatter()
        day.locale = Locale(identifier: "en_US_POSIX"); day.timeZone = zone; day.dateFormat = "yyyy-MM-dd"
        return day.date(from: String(iso.prefix(10))).map { out.string(from: $0) } ?? iso
    }

    public static func dateTime(_ iso: String?, zone: TimeZone = .current, locale: Locale = .current) -> String? {
        guard let iso, !iso.isEmpty else { return nil }
        guard let d = instant(iso) else { return date(iso, zone: zone, locale: locale) }
        let out = DateFormatter()
        out.locale = locale; out.timeZone = zone; out.dateStyle = .medium; out.timeStyle = .short
        return out.string(from: d)
    }
}
