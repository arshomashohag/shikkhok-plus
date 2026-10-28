package com.shikkhokplus.app.feature.guardian.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.feature.guardian.ChildProgressUiState
import com.shikkhokplus.app.feature.guardian.ProgressPoint
import com.shikkhokplus.app.feature.guardian.ProgressReading
import java.util.Locale

/** One batch chip. */
const val TAG_PROGRESS_BATCH: String = "progress_batch"

/** The chart. */
const val TAG_PROGRESS_CHART: String = "progress_chart"

/** The server's one-line reading. */
const val TAG_PROGRESS_READING: String = "progress_reading"

/** One row of the results table. */
const val TAG_PROGRESS_ROW: String = "progress_row"

/** The batch average line's grey, #6E7682 on the board. */
private val AverageInk = Color(0xFF6E7682)

/** The gridlines' grey, #E4E8EE on the board. */
private val GridInk = Color(0xFFE4E8EE)

/**
 * G2: one child's results in one batch, as a line against the batch
 * average, with the server's reading of the latest run.
 *
 * The chart only draws what the server sent: a missed test is left out
 * rather than drawn as a zero [BR6.6], and the average appears only
 * where the marksheet publishes one.
 *
 * @param state What to render
 * @param onBack Called to leave
 * @param onSelect Called with a batch's seat
 * @param onRetry Called to read again
 */
@Composable
fun ChildProgressScreen(
    state: ChildProgressUiState,
    onBack: () -> Unit,
    onSelect: (String) -> Unit,
    onRetry: () -> Unit,
) {
    val loaded = state as? ChildProgressUiState.Loaded
    ScreenScaffold(
        title =
            loaded?.let { stringResource(R.string.child_progress_title, Numerals.freeText(firstName(it.childName))) }
                ?: stringResource(R.string.screen_title_progress),
        subtitle = loaded?.childName?.let(Numerals::freeText),
        onBack = onBack,
    ) {
        when (state) {
            ChildProgressUiState.Loading -> SkeletonList()
            is ChildProgressUiState.Failed ->
                ErrorCard(
                    title = stringResource(R.string.progress_error_title),
                    body = stringResource(R.string.progress_error_body),
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) onRetry else null,
                )
            is ChildProgressUiState.Loaded -> Loaded(state, onSelect)
        }
    }
}

/**
 * The chips, then the reading, chart and table -- or the single test.
 *
 * @param state The loaded state
 * @param onSelect Called with a batch's seat
 */
@Composable
private fun Loaded(state: ChildProgressUiState.Loaded, onSelect: (String) -> Unit) {
    if (state.batches.size > 1) {
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            state.batches.forEach { batch ->
                BatchChip(batch.name, batch.seat == state.selected) { onSelect(batch.seat) }
            }
        }
    }
    when (state.points.size) {
        0 -> CardBox { Text(stringResource(R.string.student_results_empty)) }
        1 -> SingleTest(state.points.single())
        else -> {
            state.reading?.let { Reading(it) }
            CardBox(Modifier.padding(12.dp)) { Chart(state.childName, state.points) }
            Table(state.points)
        }
    }
}

/**
 * A batch chip, tonal with a border when chosen.
 *
 * @param name The batch
 * @param on Whether it is shown
 * @param onClick Called when tapped
 */
@Composable
private fun BatchChip(name: String, on: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    Text(
        Numerals.freeText(name),
        style = MaterialTheme.typography.titleSmall,
        color = if (on) MaterialTheme.colorScheme.onSecondaryContainer else MaterialTheme.colorScheme.onSurface,
        modifier =
            Modifier
                .heightIn(min = 44.dp)
                .background(
                    if (on) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface,
                    shape,
                )
                .border(
                    1.5.dp,
                    if (on) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
                    shape,
                )
                .clickable(onClick = onClick)
                .padding(horizontal = 16.dp, vertical = 10.dp)
                .testTag(TAG_PROGRESS_BATCH),
    )
}

/**
 * "Marks went up in each of the last 4 tests, from 31 to 44 out of 50.
 * Now above the batch average." -- every comparison the server's.
 *
 * @param reading The server's reading
 */
@Composable
private fun Reading(reading: ProgressReading) {
    val lead =
        when (reading.direction) {
            "up" -> R.string.progress_went_up
            "down" -> R.string.progress_went_down
            else -> R.string.progress_stayed
        }
    val average =
        when (reading.aboveAverage) {
            true -> stringResource(R.string.progress_above_average)
            false -> stringResource(R.string.progress_below_average)
            null -> ""
        }
    CardBox(Modifier.padding(horizontal = 16.dp, vertical = 14.dp).testTag(TAG_PROGRESS_READING)) {
        Text(
            buildAnnotatedString {
                append(stringResource(lead, Numerals.count(reading.run)))
                append(" ")
                withStyle(SpanStyle(fontWeight = FontWeight.Bold)) {
                    append(
                        stringResource(
                            R.string.progress_from_to,
                            Numerals.count(reading.firstMarks),
                            Numerals.count(reading.lastMarks),
                            Numerals.count(reading.totalMarks),
                        ),
                    )
                }
                append(". ")
                append(average)
            },
            style = MaterialTheme.typography.bodyLarge,
        )
    }
}

/**
 * The line chart: the child's marks solid, the batch average dashed.
 *
 * Scaled to the marks and averages shown, so a run from 31 to 44 out
 * of 50 fills the height rather than sitting in its top third.
 *
 * @param name The child, for the legend
 * @param points The marked tests, oldest first
 */
@Composable
private fun Chart(name: String, points: List<ProgressPoint>) {
    val primary = MaterialTheme.colorScheme.primary
    val ink = MaterialTheme.colorScheme.onSurface
    val values = points.map { it.marks.toFloat() } + points.mapNotNull { it.average?.toFloat() }
    val top = points.maxOf { it.totalMarks }.toFloat()
    val bottom = (values.minOrNull() ?: 0f).let { (it / STEP).toInt() * STEP }.toFloat().coerceAtMost(top - STEP)
    val description =
        stringResource(
            R.string.progress_chart_description,
            Numerals.freeText(name),
            points.joinToString(", ") { Numerals.count(it.marks) },
        )
    Row(Modifier.padding(bottom = 6.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Legend(Numerals.freeText(firstName(name)), primary, dashed = false)
        if (points.any { it.average != null }) Legend(
            stringResource(R.string.progress_batch_average),
            AverageInk,
            dashed = true,
        )
    }
    Row {
        Column(Modifier.width(28.dp).height(CHART_HEIGHT.dp), verticalArrangement = Arrangement.SpaceBetween) {
            listOf(top, (top + bottom) / 2, bottom).forEach {
                Text(
                    Numerals.count(it.toInt()),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Canvas(
            Modifier
                .weight(1f)
                .height(CHART_HEIGHT.dp)
                .semantics { contentDescription = description }
                .testTag(TAG_PROGRESS_CHART),
        ) { drawChart(points, bottom, top, primary) }
    }
    Row(Modifier.fillMaxWidth().padding(start = 28.dp, top = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        points.forEach {
            Text(
                shortDate(it.date),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
    val last = points.last()
    Text(
        listOfNotNull(
            "${Numerals.count(last.marks)}/${Numerals.count(last.totalMarks)}",
            last.average?.let { stringResource(R.string.progress_avg, averageLabel(it)) },
        ).joinToString(" · "),
        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
        color = ink,
        modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
    )
}

/**
 * One legend entry.
 *
 * @param label What it is
 * @param color Its line colour
 * @param dashed Whether its line is dashed
 */
@Composable
private fun Legend(label: String, color: Color, dashed: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Canvas(Modifier.width(22.dp).height(10.dp)) {
            drawLine(
                color,
                Offset(0f, size.height / 2),
                Offset(size.width, size.height / 2),
                strokeWidth = 2.dp.toPx(),
                pathEffect = if (dashed) PathEffect.dashPathEffect(floatArrayOf(8f, 6f)) else null,
            )
            if (!dashed) drawCircle(color, 4.dp.toPx(), Offset(size.width / 2, size.height / 2))
        }
        Text(label, style = MaterialTheme.typography.bodyMedium)
    }
}

/**
 * Test, marks and rank, newest first.
 *
 * @param points The marked tests, oldest first
 */
@Composable
private fun Table(points: List<ProgressPoint>) {
    CardBox(Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
        TableRow(
            stringResource(R.string.progress_test),
            stringResource(R.string.progress_marks),
            stringResource(R.string.progress_rank),
            header = true,
        )
        points.asReversed().forEach { point ->
            HorizontalDivider(color = GridInk)
            TableRow(
                Numerals.freeText(point.title),
                "${Numerals.count(point.marks)}/${Numerals.count(point.totalMarks)}",
                rankOf(point),
                modifier = Modifier.testTag(TAG_PROGRESS_ROW),
            )
        }
    }
}

/**
 * One table row.
 *
 * @param test The test
 * @param marks Its marks
 * @param rank Its rank
 * @param header Whether this is the heading row
 * @param modifier Tags
 */
@Composable
private fun TableRow(
    test: String,
    marks: String,
    rank: String,
    header: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val style =
        if (header) {
            MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold)
        } else {
            MaterialTheme.typography.bodyLarge
        }
    val color = if (header) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface
    Row(modifier.fillMaxWidth().padding(vertical = 10.dp)) {
        Text(test, style = style, color = color, modifier = Modifier.weight(1f))
        Text(
            marks,
            style = if (header) style else style.copy(fontWeight = FontWeight.Bold),
            color = color,
            modifier = Modifier.width(70.dp),
        )
        Text(rank, style = style, color = color, modifier = Modifier.width(84.dp))
    }
}

/**
 * A single test, before there is a line to draw.
 *
 * @param point The test
 */
@Composable
private fun SingleTest(point: ProgressPoint) {
    CardBox(Modifier.padding(horizontal = 16.dp, vertical = 14.dp)) {
        Text(
            "${Numerals.freeText(point.title)} · ${shortDate(point.date)}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            buildAnnotatedString {
                withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(Numerals.count(point.marks)) }
                append("/" + Numerals.count(point.totalMarks))
            },
            style = MaterialTheme.typography.headlineMedium,
        )
        val rank = point.rank
        val out = point.rankedOutOf
        val average = point.average
        if (rank != null && out != null && average != null) {
            Text(
                stringResource(
                    R.string.progress_single_rank,
                    Numerals.count(rank),
                    Numerals.count(out),
                    averageLabel(average),
                ),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
    Text(stringResource(R.string.progress_line_after_second), style = MaterialTheme.typography.bodyMedium)
}

/**
 * A white card.
 *
 * @param modifier Inner padding and tags
 * @param content Its contents
 */
@Composable
private fun CardBox(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .then(modifier),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) { content() }
}

/**
 * "5 of 19", or a dash where no rank was published.
 *
 * @param point The test
 * @return The rank
 */
@Composable
private fun rankOf(point: ProgressPoint): String {
    val rank = point.rank ?: return "–"
    val out = point.rankedOutOf ?: return Numerals.count(rank)
    return stringResource(R.string.progress_rank_of, Numerals.count(rank), Numerals.count(out))
}

/**
 * An average to one decimal place, in Latin digits.
 *
 * @param average The average mark
 * @return e.g. `36.7`
 */
private fun averageLabel(average: Double): String = String.format(Locale.ENGLISH, "%.1f", average)

/** The chart's height. */
private const val CHART_HEIGHT = 168

/** A point's radius. */
private const val POINT_RADIUS = 5

/** The y axis rounds down to a multiple of this. */
private const val STEP = 10

/**
 * Draw the gridlines, the dashed average and the child's line.
 *
 * @param points The marked tests, oldest first
 * @param bottom The axis's lowest value
 * @param top The axis's highest value
 * @param primary The child's line colour
 */
private fun DrawScope.drawChart(points: List<ProgressPoint>, bottom: Float, top: Float, primary: Color) {
    val pad = POINT_RADIUS.dp.toPx() * 2
    fun x(index: Int) = pad + (size.width - 2 * pad) * index / (points.size - 1).coerceAtLeast(1)
    fun y(value: Float) = pad + (size.height - 2 * pad) * (1 - (value - bottom) / (top - bottom))
    listOf(top, (top + bottom) / 2, bottom).forEach {
        drawLine(GridInk, Offset(0f, y(it)), Offset(size.width, y(it)), strokeWidth = 1.dp.toPx())
    }
    val averages = points.mapIndexedNotNull { i, p -> p.average?.let { Offset(x(i), y(it.toFloat())) } }
    if (averages.size > 1) {
        drawPath(
            pathThrough(averages),
            AverageInk,
            style = Stroke(width = 2.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f))),
        )
    }
    val marks = points.mapIndexed { i, p -> Offset(x(i), y(p.marks.toFloat())) }
    drawPath(pathThrough(marks), primary, style = Stroke(width = 2.dp.toPx()))
    marks.forEach {
        drawCircle(Color.White, POINT_RADIUS.dp.toPx() + 2.dp.toPx(), it)
        drawCircle(primary, POINT_RADIUS.dp.toPx(), it)
    }
}

/**
 * A line through these points, in order.
 *
 * @param points At least one point
 * @return The path
 */
private fun pathThrough(points: List<Offset>): Path =
    Path().apply {
        moveTo(points.first().x, points.first().y)
        points.drop(1).forEach { lineTo(it.x, it.y) }
    }
