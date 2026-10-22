package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.Typography
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.sp

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

private fun banglaSafe(
    sizeSp: Int,
    lineHeightSp: Int,
    weight: FontWeight,
): TextStyle = TextStyle(
    fontSize = sizeSp.sp,
    lineHeight = lineHeightSp.sp,
    fontWeight = weight,
    lineHeightStyle = BanglaSafeLineHeight,
    platformStyle = NoExtraPadding,
)

/**
 * The scale.
 *
 * Only the seven slots the design defines are overridden. The rest keep
 * M3's defaults deliberately: an unused slot with a made-up value is a
 * value nobody checked against Bangla, and leaving it default makes its
 * use obvious in review.
 */
internal val ShikhokTypography: Typography = Typography().let { base ->
    base.copy(
        displaySmall = banglaSafe(34, 52, FontWeight.Bold),
        headlineMedium = banglaSafe(26, 40, FontWeight.Bold),
        titleLarge = banglaSafe(21, 34, FontWeight.SemiBold),
        bodyLarge = banglaSafe(18, 30, FontWeight.Normal),
        bodyMedium = banglaSafe(16, 26, FontWeight.Normal),
        labelLarge = banglaSafe(14, 22, FontWeight.SemiBold),
        labelSmall = banglaSafe(13, 20, FontWeight.Medium),
    )
}
