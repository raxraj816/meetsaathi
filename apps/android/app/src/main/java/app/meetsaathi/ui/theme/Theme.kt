package app.meetsaathi.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

/** packages/design/tokens.json (master v1 tokens). */
@Immutable
data class MsColors(
    val canvas: Color, val surface: Color, val raised: Color, val border: Color, val text: Color, val secondary: Color,
    val accent: Color, val onAccent: Color, val caution: Color, val danger: Color,
)

val DarkTokens = MsColors(Color(0xFF081522), Color(0xFF132839), Color(0xFF183B38), Color(0xFF2C495A), Color(0xFFF0F8F8),
    Color(0xFFA0B8C6), Color(0xFF70E6D0), Color(0xFF092B2C), Color(0xFFFFCF8A), Color(0xFFFF9BA7))
val LightTokens = MsColors(Color(0xFFF4F8FA), Color(0xFFFFFFFF), Color(0xFFEAF6F3), Color(0xFFD6E1E6), Color(0xFF142630),
    Color(0xFF51636F), Color(0xFF087968), Color(0xFFFFFFFF), Color(0xFF9C6000), Color(0xFFA72641))

val LocalMs = staticCompositionLocalOf { DarkTokens }

object Spacing { val xs = 4.dp; val s = 8.dp; val m = 12.dp; val l = 16.dp; val xl = 24.dp; val xxl = 32.dp }
object Radii { val small = 12.dp; val card = 18.dp; val hero = 24.dp }
val MinTouch = 48.dp

@Composable
fun MeetSaathiTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val t = if (dark) DarkTokens else LightTokens
    val scheme = if (dark) darkColorScheme(primary = t.accent, onPrimary = t.onAccent, background = t.canvas, surface = t.surface,
        onBackground = t.text, onSurface = t.text, error = t.danger, secondary = t.secondary, outline = t.border)
    else lightColorScheme(primary = t.accent, onPrimary = t.onAccent, background = t.canvas, surface = t.surface,
        onBackground = t.text, onSurface = t.text, error = t.danger, secondary = t.secondary, outline = t.border)
    androidx.compose.runtime.CompositionLocalProvider(LocalMs provides t) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
