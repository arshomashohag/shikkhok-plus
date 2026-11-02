package com.shikkhokplus.app.feature.dashboard.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/**
 * The exam marks as a line, with the batch average dashed and the batch
 * highest dotted. A line the server did not send is not drawn.
 *
 * @param series The positions
 * @param ink The seat's line colour
 * @param modifier Layout modifier
 */
@Composable
fun MarksLine(
    series: MarksSeries,
    ink: Color,
    modifier: Modifier = Modifier,
) {
    val grid = MaterialTheme.colorScheme.outlineVariant
    val average = MaterialTheme.colorScheme.outline
    val highest = MaterialTheme.colorScheme.secondary
    Canvas(modifier.fillMaxWidth().height(CHART_HEIGHT).testTag(TAG_DASHBOARD_EXAM_CHART)) {
        listOf(0f, 0.5f, 1f).forEach { level ->
            val y = size.height * (1 - level)
            drawLine(grid, Offset(0f, y), Offset(size.width, y), 1.dp.toPx())
        }
        if (series.hasHighest) {
            drawSeries(series.highest, highest, dash = floatArrayOf(2.dp.toPx(), 4.dp.toPx()), round = true)
        }
        if (series.hasAverage) {
            drawSeries(series.average, average, dash = floatArrayOf(8.dp.toPx(), 5.dp.toPx()))
        }
        drawSeries(series.own, ink, dash = null, markers = true)
    }
}

private val CHART_HEIGHT = 140.dp

private fun DrawScope.drawSeries(
    values: List<Float?>,
    color: Color,
    dash: FloatArray?,
    round: Boolean = false,
    markers: Boolean = false,
) {
    val step = if (values.size > 1) size.width / (values.size - 1) else 0f
    val x = { i: Int -> if (values.size > 1) step * i else size.width / 2 }
    val y = { v: Float -> size.height * (1 - v) }
    val width = 2.5.dp.toPx()
    val effect = dash?.let { PathEffect.dashPathEffect(it) }
    var previous: Offset? = null
    values.forEachIndexed { i, value ->
        val point = value?.let { Offset(x(i), y(it)) }
        if (point != null && previous != null) {
            drawLine(
                color,
                previous!!,
                point,
                width,
                cap = if (round) StrokeCap.Round else StrokeCap.Butt,
                pathEffect = effect,
            )
        }
        if (point != null && markers) drawCircle(color, 4.dp.toPx(), point)
        previous = point
    }
    if (values.count { it != null } == 1 && !markers) {
        values.forEachIndexed { i, v -> v?.let { drawCircle(color, 3.dp.toPx(), Offset(x(i), y(it))) } }
    }
}
