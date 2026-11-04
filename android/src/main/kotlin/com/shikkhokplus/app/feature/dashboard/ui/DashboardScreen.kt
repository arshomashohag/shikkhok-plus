package com.shikkhokplus.app.feature.dashboard.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.feature.guardian.ui.firstName
import com.shikkhokplus.app.feature.dashboard.DashboardReader
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.statusColors
import com.shikkhokplus.app.core.designsystem.styleFor
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.network.DashboardExamDto
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.dashboard.DashboardChild
import com.shikkhokplus.app.feature.dashboard.DashboardDirection
import com.shikkhokplus.app.feature.dashboard.DashboardFeeMonth
import com.shikkhokplus.app.feature.dashboard.DashboardRange
import com.shikkhokplus.app.feature.dashboard.DashboardUiState
import com.shikkhokplus.app.feature.fees.StripKind

/** Stable test identifiers. Not user-visible text. */
const val TAG_DASHBOARD_LOADING: String = "dashboard_loading"

/** The error card. */
const val TAG_DASHBOARD_ERROR: String = "dashboard_error"

/** One range chip. */
const val TAG_DASHBOARD_RANGE_CHIP: String = "dashboard_range_chip"

/** One child chip. */
const val TAG_DASHBOARD_CHILD_CHIP: String = "dashboard_child_chip"

/** One batch chip. */
const val TAG_DASHBOARD_BATCH_CHIP: String = "dashboard_batch_chip"

/** One of the three tiles. */
const val TAG_DASHBOARD_TILE: String = "dashboard_tile"

/** The marks chart. */
const val TAG_DASHBOARD_EXAM_CHART: String = "dashboard_exam_chart"

/** The legend entry for the batch average line. */
const val TAG_DASHBOARD_AVERAGE_LEGEND: String = "dashboard_average_legend"

/** The legend entry for the batch highest line. */
const val TAG_DASHBOARD_HIGHEST_LEGEND: String = "dashboard_highest_legend"

/** The latest exam's row. */
const val TAG_DASHBOARD_LATEST_EXAM: String = "dashboard_latest_exam"

/** The neutral state shown when there are no marks to draw. */
const val TAG_DASHBOARD_EXAMS_EMPTY: String = "dashboard_exams_empty"

/** One month on the fee strip. */
const val TAG_DASHBOARD_FEE_MONTH: String = "dashboard_fee_month"

/** The fee history link. */
const val TAG_DASHBOARD_FEE_HISTORY: String = "dashboard_fee_history"

/** The Send money button. */
const val TAG_DASHBOARD_SEND_MONEY: String = "dashboard_send_money"

/**
 * What the dashboard's controls do.
 *
 * @property onRange A range chip was tapped
 * @property onChild A child chip was tapped, with the child's key
 * @property onBatch A batch chip was tapped, with its seat
 * @property onFeeHistory The fee History link
 * @property onSendMoney Send money, for a student or guardian
 * @property onRetry Ask again after a failure
 * @property onBack The back arrow
 */
data class DashboardActions(
    val onRange: (DashboardRange) -> Unit = {},
    val onChild: (String) -> Unit = {},
    val onBatch: (String) -> Unit = {},
    val onFeeHistory: () -> Unit = {},
    val onSendMoney: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: (() -> Unit)? = null,
)

/**
 * D1 and D2: one seat's progress, for a teacher, a student or a guardian.
 *
 * Every figure, percent and fee state is the server's. The charts only
 * turn those integers into positions; nothing is added, averaged or
 * compared here [TC-9, D-31]. When the teacher does not share marks the
 * server sends none, and this shows a neutral empty state rather than
 * an error.
 *
 * @param state What to render
 * @param actions What the controls do
 * @param modifier Layout modifier
 */
@Composable
fun DashboardScreen(
    state: DashboardUiState,
    actions: DashboardActions,
    modifier: Modifier = Modifier,
) {
    val loaded = state as? DashboardUiState.Loaded
    ScreenScaffold(
        title = loaded?.let { titleOf(it) } ?: stringResource(R.string.screen_title_progress),
        subtitle = loaded?.let { subtitleOf(it) },
        onBack = actions.onBack,
        modifier = modifier,
    ) {
        when (state) {
            DashboardUiState.Loading -> SkeletonList(modifier = Modifier.testTag(TAG_DASHBOARD_LOADING))
            is DashboardUiState.Failed ->
                // "Couldn't load the results" (G2), with the server's reason
                // under it rather than as the heading.
                ErrorCard(
                    title = stringResource(R.string.dashboard_load_failed),
                    body = stringResource(MessageKeys.resolve(state.messageKey)),
                    modifier = Modifier.testTag(TAG_DASHBOARD_ERROR),
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            is DashboardUiState.Loaded -> Dashboard(state, actions)
        }
    }
}

private fun subtitleOf(state: DashboardUiState.Loaded): String =
    listOf(state.heading.takeUnless { namesChild(state) }.orEmpty(), state.subheading)
        .filter { it.isNotBlank() }
        .joinToString(" · ") { Numerals.freeText(it) }

/**
 * "তাসনিম's progress" for a guardian (G2), whose child is the subject
 * of the screen; plain "Progress" for anyone reading their own or a
 * batch's.
 *
 * @param state The dashboard
 * @return The title
 */
@Composable
private fun titleOf(state: DashboardUiState.Loaded): String =
    if (namesChild(state)) {
        stringResource(R.string.progress_of_child, Numerals.freeText(firstName(state.heading)))
    } else {
        stringResource(R.string.screen_title_progress)
    }

/**
 * Whether the title carries the child's name, so the subtitle need not.
 *
 * @param state The dashboard
 * @return True for a guardian reading a named child
 */
private fun namesChild(state: DashboardUiState.Loaded): Boolean =
    state.reader == DashboardReader.GUARDIAN && state.heading.isNotBlank()

@Composable
private fun Dashboard(
    state: DashboardUiState.Loaded,
    actions: DashboardActions,
) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (state.children.size > 1) ChildChips(state.children, state.selectedChild, actions.onChild)
        if (state.batches.size > 1) {
            ChipRow {
                state.batches.forEach { batch ->
                    Chip(Numerals.freeText(batch.name), batch.seat == state.seat, TAG_DASHBOARD_BATCH_CHIP) {
                        actions.onBatch(batch.seat)
                    }
                }
            }
        }
        RangeChips(state.range, actions.onRange)
        Tiles(state)
        AttendanceSection(state)
        ExamsSection(state)
        FeesSection(state, actions)
    }
}

@Composable
private fun ChildChips(
    children: List<DashboardChild>,
    selected: String?,
    onChild: (String) -> Unit,
) {
    ChipRow {
        children.forEach { child ->
            Chip(Numerals.freeText(child.name), child.key == selected, TAG_DASHBOARD_CHILD_CHIP) { onChild(child.key) }
        }
    }
}

@Composable
private fun RangeChips(
    selected: DashboardRange,
    onRange: (DashboardRange) -> Unit,
) {
    ChipRow {
        DashboardRange.entries.forEach { range ->
            Chip(stringResource(rangeLabel(range)), range == selected, TAG_DASHBOARD_RANGE_CHIP) { onRange(range) }
        }
    }
}

private fun rangeLabel(range: DashboardRange): Int =
    when (range) {
        DashboardRange.SIX_MONTHS -> R.string.dashboard_range_6m
        DashboardRange.YEAR -> R.string.dashboard_range_year
        DashboardRange.ALL -> R.string.dashboard_range_all
    }

@Composable
private fun ChipRow(content: @Composable RowScope.() -> Unit) {
    Row(
        Modifier.horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        content = content,
    )
}

@Composable
private fun Chip(
    text: String,
    on: Boolean,
    tag: String,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(22.dp)
    Text(
        text,
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
                .testTag(tag),
    )
}

@Composable
private fun Tiles(state: DashboardUiState.Loaded) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Tile(
            label = stringResource(R.string.dashboard_tile_attendance),
            value = state.attendancePercent?.let { percent(it) } ?: "–",
            note =
                stringResource(
                    R.string.dashboard_tile_attendance_of,
                    Numerals.count(state.present),
                    Numerals.count(state.held),
                ),
            modifier = Modifier.weight(1f),
        )
        Tile(
            label = stringResource(R.string.dashboard_tile_exam),
            value = state.examAveragePercent?.let { percent(it) } ?: "–",
            note =
                if (state.examAveragePercent == null) {
                    stringResource(R.string.dashboard_tile_exam_none)
                } else {
                    stringResource(
                        R.string.dashboard_tile_exam_note,
                        Numerals.count(state.exams.size),
                        arrow(state.direction),
                    )
                },
            modifier = Modifier.weight(1f),
        )
        Tile(
            label = stringResource(R.string.dashboard_tile_fees),
            value = Numerals.money(state.owed),
            note = stringResource(R.string.dashboard_tile_owed),
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun Tile(
    label: String,
    value: String,
    note: String,
    modifier: Modifier = Modifier,
) {
    ShikkhokCard(modifier.testTag(TAG_DASHBOARD_TILE)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.titleLarge)
        Text(note, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private fun percent(value: Int): String = "${Numerals.count(value)}%"

private fun arrow(direction: DashboardDirection?): String =
    when (direction) {
        DashboardDirection.UP -> "↑"
        DashboardDirection.DOWN -> "↓"
        DashboardDirection.SAME -> "→"
        null -> ""
    }

@Composable
private fun AttendanceSection(state: DashboardUiState.Loaded) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.dashboard_attendance_title), style = MaterialTheme.typography.titleSmall)
        AttendanceBars(state.attendance)
    }
}

@Composable
private fun ExamsSection(state: DashboardUiState.Loaded) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.dashboard_exams_title), style = MaterialTheme.typography.titleSmall)
        if (state.exams.isEmpty()) {
            EmptyState(
                title = stringResource(R.string.dashboard_exams_empty_title),
                body = stringResource(R.string.dashboard_exams_empty_body),
                modifier = Modifier.testTag(TAG_DASHBOARD_EXAMS_EMPTY),
            )
            return
        }
        val series = marksSeries(state.exams)
        val ink = MaterialTheme.colorScheme.primary
        val description = stringResource(R.string.dashboard_exam_chart_desc, Numerals.count(state.exams.size))
        Box(Modifier.semantics { contentDescription = description }) { MarksLine(series, ink) }
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Legend(stringResource(R.string.dashboard_legend_marks), ink, Modifier)
            if (series.hasAverage) {
                Legend(
                    stringResource(R.string.dashboard_legend_average),
                    MaterialTheme.colorScheme.outline,
                    Modifier.testTag(TAG_DASHBOARD_AVERAGE_LEGEND),
                )
            }
            if (series.hasHighest) {
                Legend(
                    stringResource(R.string.dashboard_legend_highest),
                    MaterialTheme.colorScheme.secondary,
                    Modifier.testTag(TAG_DASHBOARD_HIGHEST_LEGEND),
                )
            }
        }
        LatestExam(state.exams.last())
    }
}

@Composable
private fun Legend(
    text: String,
    colour: Color,
    modifier: Modifier,
) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.size(10.dp).background(colour, RoundedCornerShape(5.dp)))
        Text(text, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun LatestExam(exam: DashboardExamDto) {
    val parts =
        buildString {
            append(exam.marks?.let { Numerals.count(it) } ?: "–")
            exam.batchAverage?.let { append(stringResource(R.string.dashboard_latest_avg, Numerals.count(it))) }
            exam.batchHighest?.let { append(stringResource(R.string.dashboard_latest_high, Numerals.count(it))) }
        }
    Row(
        Modifier.fillMaxWidth().testTag(TAG_DASHBOARD_LATEST_EXAM),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            stringResource(R.string.dashboard_latest_title, Numerals.freeText(exam.title), shortDate(exam.date)),
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f, fill = false),
        )
        Text(parts, style = MaterialTheme.typography.titleSmall)
    }
}

@Composable
private fun FeesSection(
    state: DashboardUiState.Loaded,
    actions: DashboardActions,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(stringResource(R.string.dashboard_fees_title), style = MaterialTheme.typography.titleSmall)
            TextAction(
                text = stringResource(R.string.dashboard_fees_history),
                onClick = actions.onFeeHistory,
                modifier = Modifier.testTag(TAG_DASHBOARD_FEE_HISTORY),
            )
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            state.feeMonths.forEach { FeeMonthCell(it) }
        }
        if (state.canSendMoney) {
            PrimaryButton(
                text = stringResource(R.string.dashboard_send_money),
                onClick = actions.onSendMoney,
                modifier = Modifier.fillMaxWidth().testTag(TAG_DASHBOARD_SEND_MONEY),
            )
        }
    }
}

@Composable
private fun FeeMonthCell(month: DashboardFeeMonth) {
    val style = styleFor(paymentStateOf(month.kind), MaterialTheme.statusColors)
    val name = monthName(month.period)
    val description = stringResource(R.string.fee_strip_cell_desc, name, stateWord(month.kind))
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier =
            Modifier
                .testTag(TAG_DASHBOARD_FEE_MONTH)
                .semantics(mergeDescendants = true) { contentDescription = description },
    ) {
        Box(
            Modifier
                .widthIn(min = 40.dp)
                .heightIn(min = 40.dp)
                .background(style.container, RoundedCornerShape(8.dp))
                .let { base -> style.border?.let { base.border(1.5.dp, it, RoundedCornerShape(8.dp)) } ?: base },
            contentAlignment = Alignment.Center,
        ) {
            Text(glyph(month.kind), color = style.content, style = MaterialTheme.typography.titleMedium)
        }
        Text(name, style = MaterialTheme.typography.labelSmall)
    }
}

private fun paymentStateOf(kind: StripKind): PaymentState =
    when (kind) {
        StripKind.PAID, StripKind.WAIVED -> PaymentState.PAID
        StripKind.PARTIAL -> PaymentState.PARTIAL
        StripKind.UNPAID -> PaymentState.DUE
        StripKind.CHECKING -> PaymentState.VERIFYING
    }

private fun glyph(kind: StripKind): String =
    when (kind) {
        StripKind.PAID -> "✓"
        StripKind.PARTIAL -> "½"
        StripKind.UNPAID -> "!"
        StripKind.WAIVED -> "○"
        StripKind.CHECKING -> "…"
    }

@Composable
private fun stateWord(kind: StripKind): String =
    stringResource(
        when (kind) {
            StripKind.PAID -> R.string.fees_status_paid
            StripKind.PARTIAL -> R.string.fees_status_partly_paid
            StripKind.UNPAID -> R.string.fees_status_unpaid
            StripKind.WAIVED -> R.string.fees_status_waived
            StripKind.CHECKING -> R.string.fee_strip_checking
        },
    )
