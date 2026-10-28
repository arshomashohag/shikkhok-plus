package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.draw.drawBehind

/** Stable test identifier for the chip. Not user-visible text. */
const val TAG_PAYMENT_CHIP: String = "payment_chip"

/**
 * What a fee looks like right now.
 *
 * The five states a fee can be in, as the design system defines them.
 * Each is distinguished four ways over: **colour, shape, fill style and
 * words**. That redundancy is the requirement, not decoration — with
 * colour removed entirely the five must still separate, because a
 * teacher checking dues in sunlight on a washed-out LCD is reading
 * shape and text, not hue. [PaymentStateChipStyle] records which cue
 * does the work for each.
 */
enum class PaymentState {
    /** Settled in full. */
    PAID,

    /** Something paid, a remainder outstanding. */
    PARTIAL,

    /** Nothing paid, not yet late. */
    DUE,

    /** Nothing paid and past the date. */
    OVERDUE,

    /** A claim submitted, not yet confirmed by the teacher. */
    VERIFYING,
}

/**
 * How a state is filled — the cue that survives greyscale.
 *
 * Named as its own type rather than inferred from the colours, because
 * it is a stated part of the design contract: `SOLID` belongs to
 * overdue alone, and a second solid fill would mean the loud-colour
 * budget had been spent twice. A test asserts exactly that, which it
 * could not do if the distinction only existed as two hex values that
 * happen to differ.
 */
internal enum class FillKind {
    /** A tonal wash. Paid and partial. */
    TONAL,

    /** No fill, the surface shows through. Due and verifying. */
    NONE,

    /** A full-strength fill. Overdue only. */
    SOLID,
}

/**
 * The resolved look of one state.
 *
 * @property container The fill colour
 * @property content Text and icon colour
 * @property border The outline, or null when the state is filled
 * @property fill Which fill cue this state uses
 * @property dashed Whether that outline is dashed
 */
internal data class ChipStyle(
    val container: Color,
    val content: Color,
    val border: Color?,
    val fill: FillKind,
    val dashed: Boolean = false,
) {
    /** Whether this state draws an outline at all. */
    val outlined: Boolean get() = border != null

    /** Alias, so a test reads in the vocabulary of the cue. */
    val filled: FillKind get() = fill
}

/**
 * A chip showing a payment state.
 *
 * **The label is passed in, not derived here.** A chip that built its
 * own text would be deciding what counts as due, and that is a business
 * rule the server owns [TC-9, D-31]. The caller passes the words the
 * server sent — which is also why the remainder and the day count are
 * always visible: `Partial · ৳400 left` and `Overdue 23 days` carry the
 * number in the label rather than implying it with a colour.
 *
 * @param state Which state to render
 * @param label The words to show, server-provided
 * @param modifier The layout modifier
 * @param compact The 24dp list-row size rather than the 32dp one
 */
@Composable
fun PaymentStateChip(
    state: PaymentState,
    label: String,
    modifier: Modifier = Modifier,
    compact: Boolean = false,
) {
    // The app's theme, not the system's: a screen forced light or dark
    // must get the matching chip.
    val dark = MaterialTheme.colorScheme.surface.luminance() < DARK_LUMINANCE
    val style = styleFor(state, dark)
    val radius = if (compact) 12.dp else 16.dp
    val shape: Shape = RoundedCornerShape(radius)
    val base = if (compact) MaterialTheme.typography.labelSmall else MaterialTheme.typography.labelLarge

    Row(
        modifier = modifier
            .testTag(TAG_PAYMENT_CHIP)
            // The state is named for a screen reader, which cannot see
            // the shape or the fill that carry it visually.
            .semantics { contentDescription = "${state.spoken()}: $label" }
            .defaultMinSize(minHeight = if (compact) 24.dp else 32.dp)
            .background(style.container, shape)
            .then(chipBorder(style, radius))
            .padding(horizontal = if (compact) 8.dp else 12.dp, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(if (compact) 4.dp else 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        PaymentStateIcon(state, style.content)
        Text(
            text = label,
            // Overdue is the one bold chip; the rest are 600.
            style =
                base.copy(
                    fontWeight = if (state == PaymentState.OVERDUE) FontWeight.Bold else FontWeight.SemiBold,
                ),
            color = style.content,
            // A chip is one line; a label that wrapped would read as two.
            maxLines = 1,
            softWrap = false,
        )
    }
}

/**
 * The chip's outline: none, solid, or dashed for "being checked".
 *
 * **Dashed is the cue that works without colour** for a payment not yet
 * confirmed, so it is drawn rather than approximated by a solid line.
 *
 * @param style The resolved style
 * @param radius The corner radius
 * @return The border modifier
 */
private fun chipBorder(style: ChipStyle, radius: Dp): Modifier {
    val colour = style.border ?: return Modifier
    return if (style.dashed) {
        Modifier.drawBehind {
            val stroke = 1.5.dp.toPx()
            drawRoundRect(
                color = colour,
                topLeft = Offset(stroke / 2, stroke / 2),
                size = Size(size.width - stroke, size.height - stroke),
                cornerRadius = CornerRadius(radius.toPx()),
                style =
                    Stroke(
                        width = stroke,
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 3.dp.toPx())),
                    ),
            )
        }
    } else {
        Modifier.border(BorderStroke(1.5.dp, colour), RoundedCornerShape(radius))
    }
}

/** Below this surface luminance the app is in its dark theme. */
private const val DARK_LUMINANCE = 0.5f

/**
 * Resolve the colours for a state.
 *
 * These are the design's literal values rather than theme roles,
 * because the five states are a closed vocabulary with measured
 * contrast (7:1 or better in both themes). Mapping them onto M3 roles
 * would let a theme change move them, and `error` in particular is
 * reserved for form errors — an overdue fee is not a form error.
 *
 * @param state The state to resolve
 * @param dark Whether the dark theme is active
 * @return The resolved style
 */
internal fun styleFor(state: PaymentState, dark: Boolean): ChipStyle = when (state) {
    // Tonal fill, tick in a circle.
    PaymentState.PAID -> if (dark) {
        ChipStyle(Color(0xFF10301C), Color(0xFF8FD9A6), null, FillKind.TONAL)
    } else {
        ChipStyle(Color(0xFFDCF1E2), Color(0xFF0F5427), null, FillKind.TONAL)
    }

    // Tonal fill, half-filled circle, always shows the remainder.
    PaymentState.PARTIAL -> if (dark) {
        ChipStyle(Color(0xFF3A2A0C), Color(0xFFF5C26B), null, FillKind.TONAL)
    } else {
        ChipStyle(Color(0xFFFCE8C3), Color(0xFF663C00), null, FillKind.TONAL)
    }

    // No fill, solid outline, empty circle, always shows the date.
    PaymentState.DUE -> if (dark) {
        ChipStyle(Color(0xFF15191E), Color(0xFFD7DCE3), Color(0xFF8A929E), FillKind.NONE)
    } else {
        ChipStyle(Color(0xFFFFFFFF), Color(0xFF2B3440), Color(0xFF6E7682), FillKind.NONE)
    }

    // The only solid fill in the app. Triangle, bold, day count.
    PaymentState.OVERDUE -> if (dark) {
        ChipStyle(Color(0xFFFF7A6E), Color(0xFF1F0000), null, FillKind.SOLID)
    } else {
        ChipStyle(Color(0xFFA3201A), Color(0xFFFFFFFF), null, FillKind.SOLID)
    }

    // Dashed outline — not yet confirmed — and a clock.
    PaymentState.VERIFYING -> if (dark) {
        ChipStyle(Color(0xFF2A1B45), Color(0xFFD1B8FF), Color(0xFFD1B8FF), FillKind.NONE, dashed = true)
    } else {
        ChipStyle(Color(0xFFEFE6FB), Color(0xFF5B2E9E), Color(0xFF5B2E9E), FillKind.NONE, dashed = true)
    }
}

/** The state as a screen reader should say it. */
internal fun PaymentState.spoken(): String = when (this) {
    PaymentState.PAID -> "Paid"
    PaymentState.PARTIAL -> "Partially paid"
    PaymentState.DUE -> "Due"
    PaymentState.OVERDUE -> "Overdue"
    PaymentState.VERIFYING -> "Pending verification"
}
