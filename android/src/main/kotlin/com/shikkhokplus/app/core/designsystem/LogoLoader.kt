package com.shikkhokplus.app.core.designsystem

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathMeasure
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** The animated logo loader. Not user-visible text. */
const val TAG_LOGO_LOADER: String = "logo_loader"

/** One loop of the animation, as the design fixes it. */
private const val LOOP_MS = 2400

/** The artboard's viewBox, which every coordinate below is in. */
private const val VIEW_ORIGIN_X = 20f
private const val VIEW_ORIGIN_Y = 14f
private const val VIEW_SIZE = 72f

/**
 * The brand loader: "Nod, then tick".
 *
 * **Replaces a bare `CircularProgressIndicator`**, and translates the
 * design's own five beats across one 2.4s loop:
 *
 * 1. the teacher nods (0–0.6s)
 * 2. the student nods (0.25–0.8s)
 * 3. the tick draws up out of the book (0.7–1.45s)
 * 4. the arrowhead pops and the whole mark lifts (1.4–2.0s)
 * 5. it fades, and the loop restarts (2.0–2.4s)
 *
 * The keyframe percentages are the artboard's, converted to fractions
 * of the loop rather than re-timed by eye.
 *
 * **Use it at 48dp and up**, per the design: below that the nods are
 * too small to read, and a ring is the right control instead.
 *
 * @param modifier The layout modifier
 * @param size How large to draw the mark
 * @param label What is happening, announced and shown beneath
 */
@Composable
fun LogoLoader(
    modifier: Modifier = Modifier,
    size: Dp = 96.dp,
    label: String? = null,
) {
    val transition = rememberInfiniteTransition(label = "logo-loader")
    val t by transition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec =
            infiniteRepeatable(
                animation = tween(LOOP_MS, easing = LinearEasing),
                repeatMode = RepeatMode.Restart,
            ),
        label = "loop",
    )

    val teacher = MaterialTheme.colorScheme.primary
    val student = BrandStudent
    val ground = MaterialTheme.colorScheme.background

    // **Centred in whatever space it is given, both ways.** Reported
    // from a device: the loader sat at the top of the sign-in screen
    // while the one on app startup was correctly in the middle. The
    // difference was that the startup one is wrapped in a
    // `FullScreenLoader` and these were bare, so they took only the
    // height of their own content and landed wherever the parent
    // column happened to put them — the top.
    //
    // `fillMaxSize` and a centred Box make every use centre on its own
    // rather than depending on the caller remembering to wrap it.
    Box(
        modifier = modifier.fillMaxSize().testTag(TAG_LOGO_LOADER),
        contentAlignment = Alignment.Center,
    ) {
        Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.listItem),
    ) {
        Canvas(Modifier.size(size)) {
            drawLogo(
                t = t,
                teacher = teacher,
                student = student,
                ground = ground,
            )
        }
        if (label != null) {
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                // Announced when it changes, so a screen reader says
                // what is happening rather than leaving silence.
                modifier =
                    Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
        }
        }
    }
}

/**
 * A full-screen loader, for the moment before the app knows where to go.
 *
 * @param modifier The layout modifier
 * @param label What is happening
 */
@Composable
fun FullScreenLoader(
    modifier: Modifier = Modifier,
    label: String? = null,
) {
    Column(
        modifier = modifier.fillMaxSize().padding(Spacing.section),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        LogoLoader(label = label)
    }
}

/**
 * Draw one frame of the mark.
 *
 * @param t Where in the loop, 0 to 1
 * @param teacher The teacher figure's colour
 * @param student The student figure's and the tick's colour
 * @param ground The page behind, which the book outline is drawn in
 */
internal fun DrawScope.drawLogo(
    t: Float,
    teacher: Color,
    student: Color,
    ground: Color,
) {
    // The artboard is a 72-unit square; scale it to whatever size the
    // caller asked for and translate its origin to zero.
    val unit = this.size.minDimension / VIEW_SIZE

    // Beat 1 and 2: each head dips 5 units and returns. The artboard
    // times them as percentages of the loop, offset so the student
    // follows the teacher rather than moving with them.
    val teacherDip = dip(t, peak = 0.12f, ends = 0.24f)
    val studentDip = dip(t, peak = 0.22f, ends = 0.34f)

    // Beat 5: the whole tick fades at the end of the loop.
    val tickAlpha = when {
        t < 0.70f -> 1f
        t < 0.94f -> 1f
        else -> ((1f - t) / 0.06f).coerceIn(0f, 1f)
    }

    // Beat 4: a small lift as the arrowhead lands.
    val lift = when {
        t < 0.70f -> 0f
        t < 0.77f -> -3f * ((t - 0.70f) / 0.07f)
        t < 0.84f -> -3f * (1f - (t - 0.77f) / 0.07f)
        else -> 0f
    }

    scale(unit, unit, pivot = Offset.Zero) {
        translate(-VIEW_ORIGIN_X, -VIEW_ORIGIN_Y) {
            // Teacher: head and body, in primary.
            translate(0f, teacherDip) {
                drawCircle(teacher, radius = 9f, center = Offset(40f, 33f))
            }
            drawPath(bodyPath(28f, 84f, 56f, 24f), teacher)

            // Student: a lighter step of the same blue.
            translate(0f, studentDip) {
                drawCircle(student, radius = 7f, center = Offset(64f, 42f))
            }
            drawPath(bodyPath(54f, 84f, 63f, 20f), student)

            // The open book, drawn as a gap in the ground colour.
            val book = Stroke(width = 2.4f, join = StrokeJoin.Round)
            drawPath(leftPage(), ground, style = book)
            drawPath(rightPage(), ground, style = book)

            translate(0f, lift) {
                drawTick(t, tickAlpha, student, ground)
            }
        }
    }
}

/**
 * A head's vertical offset at time [t].
 *
 * @param t Where in the loop, 0 to 1
 * @param peak When the dip is deepest
 * @param ends When the head is back at rest
 * @return The offset in artboard units, negative being up
 */
private fun dip(
    t: Float,
    peak: Float,
    ends: Float,
): Float {
    if (t >= ends) return 0f
    val depth = -5f
    return if (t < peak) {
        depth * (t / peak)
    } else {
        depth * (1f - (t - peak) / (ends - peak))
    }
}

/**
 * Beats 3 and 4: the tick draws, then its arrowhead pops.
 *
 * @param t Where in the loop
 * @param alpha The fade at the end of the loop
 * @param ink The tick's colour
 * @param ground The halo colour, which separates it from the figures
 */
private fun DrawScope.drawTick(
    t: Float,
    alpha: Float,
    ink: Color,
    ground: Color,
) {
    // Beat 3: 28% to 60% of the loop, matching @keyframes eDraw.
    val drawn = ((t - 0.28f) / 0.32f).coerceIn(0f, 1f)
    if (drawn <= 0f) return

    val full = Path().apply {
        moveTo(46f, 72f)
        lineTo(53f, 80f)
        lineTo(79f, 41.5f)
    }
    val measure = PathMeasure().apply { setPath(full, false) }
    val partial = Path()
    measure.getSegment(0f, measure.length * drawn, partial, true)

    // The halo first, then the mark: the design draws the tick twice,
    // a wide stroke in the ground colour under a narrow one in blue,
    // so it reads against both figures.
    drawPath(
        partial,
        ground,
        alpha = alpha,
        style = Stroke(width = 8f, cap = StrokeCap.Round, join = StrokeJoin.Round),
    )
    drawPath(
        partial,
        ink,
        alpha = alpha,
        style = Stroke(width = 4f, cap = StrokeCap.Round, join = StrokeJoin.Round),
    )

    // Beat 4: the arrowhead pops from nothing, overshoots, settles.
    val pop = when {
        t < 0.57f -> 0f
        t < 0.67f -> 1.3f * ((t - 0.57f) / 0.10f)
        t < 0.73f -> 1.3f - 0.3f * ((t - 0.67f) / 0.06f)
        else -> 1f
    }
    if (pop <= 0f) return

    val head = Path().apply {
        moveTo(85.6f, 31.8f)
        lineTo(84.7f, 42.1f)
        lineTo(76.4f, 36.5f)
        close()
    }
    // Scales about its own centre, so it grows in place.
    scale(pop, pop, pivot = Offset(82.2f, 36.8f)) {
        drawPath(head, ground, alpha = alpha, style = Stroke(width = 4f, join = StrokeJoin.Round))
        drawPath(head, ink, alpha = alpha)
    }
}

/**
 * One figure's body: a rounded shoulder line down to the base.
 *
 * @param left The left edge
 * @param bottom The base line
 * @param shoulder Where the curve starts
 * @param width How wide the body is
 * @return The path
 */
private fun bodyPath(
    left: Float,
    bottom: Float,
    shoulder: Float,
    width: Float,
): Path =
    Path().apply {
        val radius = width / 2f
        moveTo(left, bottom)
        lineTo(left, shoulder)
        // The artboard's `a 12 12 0 0 1 24 0` — a half-round top.
        arcTo(
            rect =
                androidx.compose.ui.geometry.Rect(
                    left = left,
                    top = shoulder - radius,
                    right = left + width,
                    bottom = shoulder + radius,
                ),
            startAngleDegrees = 180f,
            sweepAngleDegrees = 180f,
            forceMoveTo = false,
        )
        lineTo(left + width, bottom)
        close()
    }

/**
 * The book's left page.
 *
 * @return The path
 */
private fun leftPage(): Path =
    Path().apply {
        moveTo(40f, 63f)
        cubicTo(46f, 63f, 50f, 65f, 53f, 68f)
        lineTo(53f, 84f)
        cubicTo(50f, 81f, 46f, 80f, 40f, 80f)
        close()
    }

/**
 * The book's right page.
 *
 * @return The path
 */
private fun rightPage(): Path =
    Path().apply {
        moveTo(66f, 63f)
        cubicTo(60f, 63f, 56f, 65f, 53f, 68f)
        lineTo(53f, 84f)
        cubicTo(56f, 81f, 60f, 80f, 66f, 80f)
        close()
    }
