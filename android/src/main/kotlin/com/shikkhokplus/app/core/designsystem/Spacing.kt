package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.ui.unit.dp

/**
 * Spacing, shape and reach, as the design system fixes them.
 *
 * Each spacing step has one stated job. The point of naming them is
 * that a gap chosen by eye drifts: `Spacing.section` says what the
 * 24dp is for, so the next person changes it deliberately or not at
 * all.
 *
 * **Depth is carried by surface tone, not shadow.** There are no
 * elevations anywhere except bottom sheets. Tone is cheaper to draw on
 * a low-end GPU and it survives sunlight, where a 2dp shadow is simply
 * invisible.
 */
object Spacing {
    /** Icon to its label. */
    val iconLabel = 4.dp

    /** Inside chips, and between stacked lines of one item. */
    val tight = 8.dp

    /** Between list items inside one card. */
    val listItem = 12.dp

    /** Screen margin, and card padding. The default. */
    val screen = 16.dp

    /** Between sections. */
    val section = 24.dp

    /**
     * Above a money decision.
     *
     * Wider than [section] on purpose: it separates an approve or
     * reject control from whatever sits above it, so a scroll that
     * lands mid-gesture cannot put a money button under the thumb.
     */
    val moneyDecision = 32.dp
}

/**
 * Minimum touch and row heights.
 *
 * **48dp is the floor for anything tappable.** A button that moves
 * money is 56dp and full width — it is the one control where an
 * accidental near-miss costs a teacher real money, so it is made hard
 * to miss rather than merely compliant.
 */
object Reach {
    /** Minimum for any tappable thing. */
    val touch = 48.dp

    /** A button that moves money: this tall, and full width. */
    val moneyButton = 56.dp

    /** A single-line list row. */
    val rowSingle = 56.dp

    /** A two-line list row. */
    val rowTwoLine = 72.dp

    /** A marks-entry row. */
    val rowMarksEntry = 64.dp

    /** A read-only marksheet row. */
    val rowMarksheet = 48.dp
}

/**
 * Corner radii.
 *
 * Mapped onto M3's [Shapes] slots so `MaterialTheme.shapes` carries
 * them and a component picks the right one by default:
 * fields 8 (small), cards 12 (medium), chips and sheets 16 (large).
 */
internal val ShikhokShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp),
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(12.dp),
    large = RoundedCornerShape(16.dp),
    extraLarge = RoundedCornerShape(16.dp),
)
