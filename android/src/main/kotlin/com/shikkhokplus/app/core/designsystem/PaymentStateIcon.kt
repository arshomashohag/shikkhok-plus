package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

/**
 * One icon per payment state, each a different shape.
 *
 * **Drawn rather than imported, because the shapes are the cue.** The
 * design distinguishes the five states without colour, and the icons
 * are half of how: a tick, a half-filled circle, an empty circle, a
 * triangle and a clock read apart in greyscale and at a glance. A
 * generic icon set would give five glyphs that differ in detail but
 * share a silhouette, which defeats the point — and pulling an icon
 * dependency in to get them would add a library for five paths.
 *
 * Marked `aria-hidden` in effect: the chip's own `contentDescription`
 * names the state, so the icon adds nothing for a screen reader and
 * announcing it twice would be noise.
 *
 * @param state Which state's icon to draw
 * @param tint The icon colour, matched to the chip's content colour
 * @param modifier The layout modifier
 */
@Composable
internal fun PaymentStateIcon(
    state: PaymentState,
    tint: Color,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier.size(16.dp)) {
        val w = size.width
        val h = size.height
        val stroke = Stroke(
            width = w * 0.125f,
            cap = StrokeCap.Round,
            join = StrokeJoin.Round,
        )
        val r = w * 0.40625f
        val centre = androidx.compose.ui.geometry.Offset(w / 2f, h / 2f)

        when (state) {
            // A tick inside a circle.
            PaymentState.PAID -> {
                drawCircle(tint, radius = r, center = centre, style = stroke)
                val tickPath = Path().apply {
                    moveTo(w * 0.3125f, h * 0.519f)
                    lineTo(w * 0.4375f, h * 0.644f)
                    lineTo(w * 0.6875f, h * 0.375f)
                }
                drawPath(tickPath, tint, style = stroke)
            }

            // A circle with its left half filled: some of it is paid.
            PaymentState.PARTIAL -> {
                drawCircle(tint, radius = r, center = centre, style = stroke)
                val half = Path().apply {
                    moveTo(w / 2f, h / 2f - r)
                    arcTo(
                        rect = androidx.compose.ui.geometry.Rect(
                            centre - androidx.compose.ui.geometry.Offset(r, r),
                            centre + androidx.compose.ui.geometry.Offset(r, r),
                        ),
                        startAngleDegrees = -90f,
                        sweepAngleDegrees = -180f,
                        forceMoveTo = false,
                    )
                    close()
                }
                drawPath(half, tint)
            }

            // An empty circle: nothing paid yet.
            PaymentState.DUE ->
                drawCircle(tint, radius = r, center = centre, style = stroke)

            // A warning triangle. The only state with a non-round mark.
            PaymentState.OVERDUE -> {
                val triangle = Path().apply {
                    moveTo(w / 2f, h * 0.125f)
                    lineTo(w * 0.9375f, h * 0.8125f)
                    lineTo(w * 0.0625f, h * 0.8125f)
                    close()
                }
                drawPath(triangle, tint, style = stroke)
                // The bang, so the triangle is not just a shape.
                drawLine(
                    tint,
                    start = androidx.compose.ui.geometry.Offset(w / 2f, h * 0.375f),
                    end = androidx.compose.ui.geometry.Offset(w / 2f, h * 0.5625f),
                    strokeWidth = stroke.width,
                    cap = StrokeCap.Round,
                )
                drawCircle(
                    tint,
                    radius = w * 0.0625f,
                    center = androidx.compose.ui.geometry.Offset(w / 2f, h * 0.6875f),
                )
            }

            // A clock: submitted, waiting on someone.
            PaymentState.VERIFYING -> {
                drawCircle(tint, radius = r, center = centre, style = stroke)
                drawLine(
                    tint,
                    start = centre,
                    end = androidx.compose.ui.geometry.Offset(w / 2f, h * 0.3125f),
                    strokeWidth = stroke.width,
                    cap = StrokeCap.Round,
                )
                drawLine(
                    tint,
                    start = centre,
                    end = androidx.compose.ui.geometry.Offset(w * 0.6875f, h / 2f),
                    strokeWidth = stroke.width,
                    cap = StrokeCap.Round,
                )
            }
        }
    }
}
