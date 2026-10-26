package app.meetsaathi.core

import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/** Server timestamps are UTC instants; people read them in their own time zone and locale. */
object Dates {
    private fun instant(iso: String): Instant? =
        runCatching { OffsetDateTime.parse(iso).toInstant() }.getOrNull() ?: runCatching { Instant.parse(iso) }.getOrNull()

    fun date(iso: String?, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String? {
        if (iso.isNullOrBlank()) return null
        val f = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(locale)
        instant(iso)?.let { return f.format(it.atZone(zone)) }
        return runCatching { f.format(LocalDate.parse(iso.take(10))) }.getOrDefault(iso)
    }

    fun dateTime(iso: String?, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String? {
        if (iso.isNullOrBlank()) return null
        val t = instant(iso) ?: return date(iso, zone, locale)
        return DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT).withLocale(locale).format(t.atZone(zone))
    }
}
