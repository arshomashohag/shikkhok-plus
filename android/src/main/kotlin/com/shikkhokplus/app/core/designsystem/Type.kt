package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.Typography
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.sp
import com.shikkhokplus.app.R

/**
 * The type scale, set for Bangla rather than for Latin.
 *
 * **Line height is at least 1.53x the size on every step.** That is the
 * whole reason this file exists instead of M3's default `Typography`.
 * M3's 1.25-1.4x ratios were built for Latin and clip Bangla
 * conjuncts: a stack like `র্ধ্ব` or `স্ত্রী` carries a reph above the
 * line and a `ু`/`ূ`/`ৃ` below it, and at 1.2x the tops and tails are
 * cut off. The interface is English, but names, topics and notices are
 * usually Bangla [TC-15, D-43], so the worst Bangla case sets the
 * metric for every step — including the ones that only ever hold
 * English.
 *
 * **Three settings make that hold at runtime**, and all three are
 * needed:
 *
 * 1. an explicit `lineHeight` on every style, which is below;
 * 2. [LineHeightStyle] with `Trim.None`, so the first and last lines
 *    keep their leading instead of being trimmed flush — trimming is
 *    exactly what reintroduces the clipping;
 * 3. `includeFontPadding = false`, so the padding is not applied twice
 *    on top of our own.
 *
 * A fixed-height text box defeats all three, so screens must not set
 * one.
 *
 * Sizes are in sp and follow the system font scale to 200%. Layouts
 * are checked at 130%.
 *
 * **Guardian screens shift one step up the same scale** — body becomes
 * reading, title becomes headline — so no large-text mode is needed.
 * An amount on a guardian screen never renders below `headlineMedium`.
 *
 * The named steps map onto M3 slots as:
 *
 * | Design step | M3 slot        | sp / line | Use                     |
 * |-------------|----------------|-----------|-------------------------|
 * | display     | displaySmall   | 34 / 52   | Money totals            |
 * | headline    | headlineMedium | 26 / 40   | Screen title, guardian  |
 * | title       | titleLarge     | 21 / 34   | Card and section titles |
 * | reading     | bodyLarge      | 18 / 30   | Guardian body, list 1st |
 * | body        | bodyMedium     | 16 / 26   | Teacher, student body   |
 * | label       | labelLarge     | 14 / 22   | Chips, buttons, headers |
 * | caption     | labelSmall     | 13 / 20   | The floor. Nothing less. |
 */

/**
 * Keeps the leading on the first and last line.
 *
 * `Trim.None` is the load-bearing value. The default trims the first
 * ascent and last descent flush to the box, which removes the space
 * the Bangla reph and vowel marks occupy.
 */
private val BanglaSafeLineHeight = LineHeightStyle(
    alignment = LineHeightStyle.Alignment.Center,
    trim = LineHeightStyle.Trim.None,
)

/** Suppresses Android's own font padding so ours is not doubled. */
@Suppress("DEPRECATION")
private val NoExtraPadding = PlatformTextStyle(includeFontPadding = false)

/**
 * Noto Sans with Noto Sans Bengali, the design's typeface on every board.
 *
 * **One font file per weight holds both scripts** (built by
 * `android/fonts/build_fonts.py`). Compose picks one font per weight and
 * leaves any glyph it lacks to the system, so a Latin-only Noto would
 * still have rendered Bangla in whatever the phone's maker ships, and
 * the app rendered everything in Roboto before this was bundled — with
 * SemiBold synthesised, since Roboto has no 600.
 */
val NotoSans: FontFamily =
    FontFamily(
        Font(R.font.noto_regular, FontWeight.Normal),
        Font(R.font.noto_medium, FontWeight.Medium),
        Font(R.font.noto_semibold, FontWeight.SemiBold),
        Font(R.font.noto_bold, FontWeight.Bold),
        Font(R.font.noto_extrabold, FontWeight.ExtraBold),
    )

private fun banglaSafe(
    sizeSp: Int,
    lineHeightSp: Int,
    weight: FontWeight,
): TextStyle = TextStyle(
    fontFamily = NotoSans,
    fontSize = sizeSp.sp,
    lineHeight = lineHeightSp.sp,
    fontWeight = weight,
    lineHeightStyle = BanglaSafeLineHeight,
    platformStyle = NoExtraPadding,
)

/**
 * The scale.
 *
 * **Every one of M3's fifteen slots is mapped onto the design's seven
 * steps** (TypeScale.dc.html: display, headline, title, reading, body,
 * label, caption). None keeps a Material default.
 *
 * This used to override only the seven, leaving the rest at M3's
 * defaults on the reasoning that an unused slot would make its use
 * obvious in review. They were not unused: `titleMedium`, `bodySmall`,
 * `titleSmall` and `labelMedium` were used throughout the screens, so
 * much of the app's text was off the scale, two of the four below the
 * design's 13sp floor, and all four under the 1.53 line-height ratio
 * that keeps Bangla conjuncts from clipping. Review did not catch it,
 * which is the case for making the rule mechanical rather than visible:
 * every slot is now a design step, and TypographyScaleTest fails if one
 * drops below the floor or the ratio.
 */
internal val ShikkhokTypography: Typography = Typography().let { base ->
    base.copy(
        displaySmall = banglaSafe(34, 52, FontWeight.Bold),
        headlineMedium = banglaSafe(26, 40, FontWeight.Bold),
        titleLarge = banglaSafe(21, 34, FontWeight.SemiBold),
        bodyLarge = banglaSafe(18, 30, FontWeight.Normal),
        bodyMedium = banglaSafe(16, 26, FontWeight.Normal),
        labelLarge = banglaSafe(14, 22, FontWeight.SemiBold),
        labelSmall = banglaSafe(13, 20, FontWeight.Medium),
        // The eight slots the design does not name, each onto the step
        // its role matches. Same sizes as a design step, never between.
        displayLarge = banglaSafe(34, 52, FontWeight.Bold),
        displayMedium = banglaSafe(34, 52, FontWeight.Bold),
        headlineLarge = banglaSafe(26, 40, FontWeight.Bold),
        headlineSmall = banglaSafe(26, 40, FontWeight.Bold),
        titleMedium = banglaSafe(16, 26, FontWeight.SemiBold),
        titleSmall = banglaSafe(14, 22, FontWeight.SemiBold),
        bodySmall = banglaSafe(13, 20, FontWeight.Normal),
        labelMedium = banglaSafe(13, 20, FontWeight.Medium),
    )
}
