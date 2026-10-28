package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** The branding hero. Not user-visible text. */
const val TAG_BRAND_HERO: String = "brand_hero"

/**
 * The blue branding band at the top of the sign-in screens.
 *
 * **`O2`'s `.hero`**, which the app did not have: a solid primary
 * band carrying the mark, the wordmark and a tagline. The screens
 * opened straight into a text field instead, so nothing said what the
 * app was before asking for a phone number.
 *
 * The artboard draws it at two sizes and the difference is deliberate:
 * tall on the empty first screen, and compact once the person has
 * started typing, so the keyboard does not push the field off. That is
 * [compact].
 *
 * The mark is `clearAndSetSemantics` with no label because the
 * wordmark beneath it says the same thing — a screen reader
 * announcing "ShikkhokPlus logo, ShikkhokPlus" reads the name twice.
 *
 * @param modifier The layout modifier
 * @param compact Whether to draw the shorter band
 * @param tagline A line under the name, on the tall band only
 */
@Composable
fun BrandHero(
    modifier: Modifier = Modifier,
    compact: Boolean = false,
    tagline: String? = null,
) {
    // **Brand colours, fixed in both themes** (O2's hero): a blue band,
    // a white teacher, and the student, the tick and "Plus" in #A9C7FF.
    // Reading them from the scheme turned the band pale blue in dark
    // mode and drew the accent in the paler #D8E3F7.
    val onHero = BrandInk
    val accent = BrandAccent
    val ground = BrandBlue

    Surface(
        modifier = modifier.fillMaxWidth().testTag(TAG_BRAND_HERO),
        color = BrandBlue,
    ) {
        Column(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(
                        top = if (compact) 28.dp else 48.dp,
                        bottom = if (compact) 22.dp else 32.dp,
                        start = Spacing.section,
                        end = Spacing.section,
                    ),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Mark(
                size = if (compact) 56.dp else 84.dp,
                figure = onHero,
                accent = accent,
                ground = ground,
            )
            Text(
                text = wordmark(accent = accent),
                style = MaterialTheme.typography.headlineMedium,
                fontSize = if (compact) 24.sp else 30.sp,
                lineHeight = if (compact) 34.sp else 40.sp,
                fontWeight = FontWeight.ExtraBold,
                color = onHero,
            )
            if (!compact && tagline != null) {
                Text(
                    text = tagline,
                    style = MaterialTheme.typography.bodyMedium.copy(fontSize = 15.sp, lineHeight = 24.sp),
                    color = BrandTagline,
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}

/**
 * "Shikkhok" in the hero's ink, "Plus" in its accent.
 *
 * @param accent The colour the second half takes
 * @return The styled wordmark
 */
@Composable
private fun wordmark(accent: androidx.compose.ui.graphics.Color) =
    buildAnnotatedString {
        append("Shikkhok")
        withStyle(SpanStyle(color = accent)) { append("Plus") }
    }

/**
 * The logo mark, drawn still.
 *
 * Reuses the loader's drawing at a settled frame rather than a second
 * copy of the paths: one definition means the still mark and the
 * animation cannot drift apart.
 *
 * @param size How large to draw it
 * @param figure The teacher figure's colour
 * @param accent The student figure's and the tick's colour
 * @param ground The colour behind, which the book outline is cut from
 */
/**
 * The logo mark on its own, for a title row.
 *
 * `O1` pairs a 40dp mark with "Create account" in its `.top` band
 * rather than using the full hero: a form screen with a branding band
 * pushes its first field below the fold.
 *
 * @param modifier The layout modifier
 * @param size How large to draw it
 */
@Composable
fun BrandMark(
    modifier: Modifier = Modifier,
    size: Dp = 40.dp,
) {
    // The mark on a light page (O1): the teacher in the brand blue and
    // the student a lighter step of it, #5B8ED6 — not the slate
    // secondary, which drew the student grey.
    val primary = BrandBlue
    val secondary = BrandStudent
    val background = MaterialTheme.colorScheme.surface

    Canvas(
        modifier
            .size(size)
            .clearAndSetSemantics { },
    ) {
        drawLogo(
            t = 0.69f,
            teacher = primary,
            student = secondary,
            ground = background,
        )
    }
}

@Composable
private fun Mark(
    size: Dp,
    figure: androidx.compose.ui.graphics.Color,
    accent: androidx.compose.ui.graphics.Color,
    ground: androidx.compose.ui.graphics.Color,
) {
    Canvas(
        Modifier
            .size(size)
            // The wordmark below says the name; announcing the mark
            // too would read it twice.
            .clearAndSetSemantics { },
    ) {
        // A settled frame: heads at rest, tick fully drawn, arrowhead
        // at full size. 0.69 sits after the pop and before the fade.
        drawLogo(t = 0.69f, teacher = figure, student = accent, ground = ground)
    }
}

/** The hero's ground. */
private val BrandBlue = Color(0xFF1D4F91)

/** The teacher figure and the wordmark on the hero. */
private val BrandInk = Color(0xFFFFFFFF)

/** The student figure, the tick and "Plus" on the hero. */
private val BrandAccent = Color(0xFFA9C7FF)

/** The hero's tagline. */
private val BrandTagline = Color(0xFFD8E3F7)

/** The student figure on a light page. */
internal val BrandStudent = Color(0xFF5B8ED6)
