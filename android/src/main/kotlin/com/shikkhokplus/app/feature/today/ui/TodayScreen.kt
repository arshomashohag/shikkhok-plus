package com.shikkhokplus.app.feature.today.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.TonalButton
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayHeading
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.today.ClassRow
import com.shikkhokplus.app.feature.today.ClassStatus
import com.shikkhokplus.app.feature.today.OwedSummary
import com.shikkhokplus.app.feature.today.TodayUiState
import com.shikkhokplus.app.feature.verify.ClaimCard
import com.shikkhokplus.app.feature.verify.Comparison

/** The money-owed card, which opens Dues. */
const val TAG_TODAY_OWED: String = "today_owed"

/** One class row. */
const val TAG_TODAY_CLASS: String = "today_class"

/** A class row's Record button. */
const val TAG_TODAY_RECORD: String = "today_record"

/** A class row's Marks button. */
const val TAG_TODAY_MARKS: String = "today_marks"

/** "See all" on the payments to check. */
const val TAG_TODAY_SEE_ALL: String = "today_see_all"

/** The first-run steps. */
const val TAG_TODAY_FIRST_RUN: String = "today_first_run"

/** Hours on a 12-hour clock. */
private const val NOON = 12

/**
 * T1: the teacher's day — what is owed, today's classes, payments to check.
 *
 * Every figure, every "next" and every "in 35 min" is the server's; the
 * screen formats them and decides nothing [TC-9].
 *
 * @param state What to render
 * @param onOpenDues Called to open Dues
 * @param onRecord Called with a class to record
 * @param onMarks Called with an exam id to enter marks
 * @param onVerifyAll Called to open the payments to check
 * @param onCreateBatch Called to start the first batch
 * @param onRetry Called to read the day again
 * @param modifier The layout modifier
 * @param bottomBar The teacher's tab bar
 * @param pending Topics saved on the phone and not yet sent, by class
 * @param notice A line to show above the day, such as a save result
 */
@Composable
fun TodayScreen(
    state: TodayUiState,
    onOpenDues: () -> Unit,
    onRecord: (ClassRow) -> Unit,
    onMarks: (String) -> Unit,
    onVerifyAll: () -> Unit,
    onCreateBatch: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
    pending: Map<String, String> = emptyMap(),
    notice: @Composable () -> Unit = {},
) {
    val date =
        when (state) {
            is TodayUiState.Loaded -> state.date
            is TodayUiState.FirstRun -> state.date
            else -> null
        }
    ScreenScaffold(
        title = stringResource(R.string.today_title),
        subtitle = date?.let(::dayHeading),
        modifier = modifier,
        bottomBar = bottomBar,
    ) {
        notice()
        when (state) {
            TodayUiState.Loading -> {
                Section(stringResource(R.string.today_classes))
                SkeletonList(rows = 2)
                Section(stringResource(R.string.today_to_verify))
                SkeletonList(rows = 2)
            }
            is TodayUiState.FirstRun -> FirstRun(onCreateBatch)
            is TodayUiState.Loaded -> Day(state, pending, onOpenDues, onRecord, onMarks, onVerifyAll)
            is TodayUiState.Failed ->
                ErrorCard(
                    title = stringResource(R.string.today_load_failed),
                    body = stringResource(MessageKeys.resolve(state.messageKey)),
                    retryLabel = stringResource(R.string.roster_retry).takeIf { state.retryable },
                    onRetry = onRetry.takeIf { state.retryable },
                )
        }
    }
}

/**
 * The loaded day, top to bottom as T1 orders it.
 *
 * @param state The day
 * @param pending Topics saved on the phone and not yet sent, by class
 * @param onOpenDues Called to open Dues
 * @param onRecord Called with a class to record
 * @param onMarks Called with an exam id
 * @param onVerifyAll Called to open the payments to check
 */
@Composable
private fun ColumnScope.Day(
    state: TodayUiState.Loaded,
    pending: Map<String, String>,
    onOpenDues: () -> Unit,
    onRecord: (ClassRow) -> Unit,
    onMarks: (String) -> Unit,
    onVerifyAll: () -> Unit,
) {
    OwedCard(state.owed, onOpenDues)

    Section(stringResource(R.string.today_classes_count, Numerals.count(state.classes.size)))
    if (state.classes.isEmpty()) {
        Quiet(stringResource(R.string.today_no_classes))
    } else {
        RowCard {
            state.classes.forEachIndexed { index, row ->
                if (index > 0) Divider()
                ClassRowView(row, pending[row.sessionId], onRecord, onMarks)
            }
        }
    }

    Section(stringResource(R.string.today_to_verify_count, Numerals.count(state.toVerifyCount))) {
        if (state.toVerifyCount > 0) {
            TextAction(
                stringResource(R.string.today_see_all),
                onVerifyAll,
                Modifier.testTag(TAG_TODAY_SEE_ALL),
            )
        }
    }
    if (state.toVerify.isEmpty()) {
        Quiet(stringResource(R.string.today_nothing_to_verify))
    } else {
        RowCard {
            state.toVerify.forEachIndexed { index, card ->
                if (index > 0) Divider()
                VerifyPreviewRow(card, onVerifyAll)
            }
        }
    }
}

/**
 * What is owed, with what is overdue as the one loud chip; opens Dues.
 *
 * @param owed The totals
 * @param onOpen Called when tapped
 */
@Composable
private fun OwedCard(owed: OwedSummary, onOpen: () -> Unit) {
    ShikkhokCard(Modifier.testTag(TAG_TODAY_OWED), onClick = onOpen) {
        Text(
            stringResource(R.string.today_outstanding, Numerals.count(owed.batchCount)),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                Numerals.money(owed.total),
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.weight(1f),
            )
            Text("›", style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.outline)
        }
        if (owed.showOverdue) {
            PaymentStateChip(
                PaymentState.OVERDUE,
                stringResource(
                    R.string.today_overdue,
                    Numerals.money(owed.overdue),
                    Numerals.count(owed.overdueStudents),
                ),
                compact = true,
            )
        }
    }
}

/**
 * One class: its time, what it is, where it stands, and its action.
 *
 * @param row The class
 * @param unsent A topic saved on the phone and not yet sent, if any
 * @param onRecord Called to record it
 * @param onMarks Called with its exam id
 */
@Composable
private fun ClassRowView(
    row: ClassRow,
    unsent: String?,
    onRecord: (ClassRow) -> Unit,
    onMarks: (String) -> Unit,
) {
    val cancelled = row.status == ClassStatus.CANCELLED
    ListRow(
        modifier =
            Modifier
                .then(if (row.isNext) Modifier.background(MaterialTheme.colorScheme.surfaceContainer) else Modifier)
                .testTag(TAG_TODAY_CLASS),
    ) {
        TimeColumn(row.startTime)
        Column(Modifier.weight(1f)) {
            Text(
                listOfNotNull(row.subjectName, row.batchName).joinToString(" · ") { Numerals.freeText(it) },
                style = MaterialTheme.typography.titleMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (unsent != null) {
                Text(
                    stringResource(R.string.today_saved_not_sent),
                    style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (unsent.isNotBlank()) {
                    Text(
                        Numerals.freeText(unsent),
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            } else {
                ClassStatusLine(row, cancelled)
            }
        }
        val examId = row.examId
        when {
            examId != null ->
                TonalButton(
                    stringResource(R.string.today_marks),
                    { onMarks(examId) },
                    Modifier.testTag(TAG_TODAY_MARKS),
                )
            !cancelled && row.topic == null && unsent == null ->
                TonalButton(
                    stringResource(R.string.today_record),
                    { onRecord(row) },
                    Modifier.testTag(TAG_TODAY_RECORD),
                )
        }
    }
}

/**
 * The line under a class: its topic, when it starts, its exam, or that
 * it was called off.
 *
 * @param row The class
 * @param cancelled Whether it was called off
 */
@Composable
private fun ClassStatusLine(row: ClassRow, cancelled: Boolean) {
    val small = MaterialTheme.typography.bodySmall
    val quiet = MaterialTheme.colorScheme.onSurfaceVariant
    val examTitle = row.examTitle
    val topic = row.topic
    val startsIn = row.startsInMinutes
    when {
        cancelled -> Text(stringResource(R.string.today_cancelled), style = small, color = quiet)
        examTitle != null ->
            Text(stringResource(R.string.today_exam, Numerals.freeText(examTitle)), style = small, color = quiet)
        topic != null ->
            Text(
                "✓ ${Numerals.freeText(topic)}",
                style = small,
                color = quiet,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        row.isNext && startsIn != null ->
            Text(
                stringResource(R.string.today_next_in, Numerals.count(startsIn)),
                style = small.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.primary,
            )
        else -> Text(stringResource(R.string.today_not_recorded), style = small, color = quiet)
    }
}

/**
 * The 56dp time column: `4:00` over `pm`.
 *
 * @param hhmm The start, `HH:MM`
 */
@Composable
private fun TimeColumn(hhmm: String) {
    val (hour, minute) = hhmm.split(":").map(String::toInt)
    val twelve = if (hour % NOON == 0) NOON else hour % NOON
    Column(Modifier.width(56.dp)) {
        Text(
            "%d:%02d".format(java.util.Locale.ENGLISH, twelve, minute),
            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
        )
        Text(
            displayTime(hhmm).substringAfter(' '),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * A payment waiting, as Today previews it; opens the queue.
 *
 * @param card The claim
 * @param onOpen Called when tapped
 */
@Composable
private fun VerifyPreviewRow(card: ClaimCard, onOpen: () -> Unit) {
    ListRow(Modifier.clickable(onClick = onOpen)) {
        Box(
            Modifier.size(40.dp).background(MaterialTheme.colorScheme.surfaceContainerHigh, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Text(card.displayName.trim().take(1), style = MaterialTheme.typography.titleMedium)
        }
        Column(Modifier.weight(1f)) {
            Text(Numerals.freeText(card.displayName), style = MaterialTheme.typography.titleMedium, maxLines = 1)
            Text(
                "${card.channel} · ${monthName(card.period)} · ${ago(card.submittedAt)}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(
                Numerals.money(card.claimedAmount),
                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
            )
            Text(
                if (card.comparison == Comparison.MATCHES) {
                    stringResource(R.string.today_matches_fee)
                } else {
                    stringResource(R.string.today_of_fee, Numerals.money(card.charged))
                },
                style = MaterialTheme.typography.bodySmall,
                color =
                    if (card.comparison == Comparison.SHORT) PartialInk else MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.End,
            )
        }
    }
}

/**
 * The first run: how to start, before any batch exists.
 *
 * @param onCreateBatch Called to start the first batch
 */
@Composable
private fun FirstRun(onCreateBatch: () -> Unit) {
    ShikkhokCard(Modifier.testTag(TAG_TODAY_FIRST_RUN)) {
        Text(stringResource(R.string.today_first_run_title), style = MaterialTheme.typography.titleMedium)
        val steps = listOf(R.string.today_step_one, R.string.today_step_two, R.string.today_step_three)
        steps.forEachIndexed { index, step ->
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(
                    Modifier.size(24.dp).background(MaterialTheme.colorScheme.primaryContainer, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        Numerals.count(index + 1),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                }
                Text(stringResource(step), style = BodyCompact, modifier = Modifier.weight(1f))
            }
        }
        PrimaryButton(stringResource(R.string.today_create_batch), onCreateBatch, Modifier.fillMaxWidth())
    }
    Section(stringResource(R.string.today_classes))
    Quiet(stringResource(R.string.today_classes_empty))
    Section(stringResource(R.string.today_to_verify))
    Quiet(stringResource(R.string.today_to_verify_empty))
}

/**
 * A section heading, with an optional action at its end.
 *
 * @param text The heading
 * @param action Drawn at the end
 */
@Composable
private fun Section(text: String, action: @Composable RowScope.() -> Unit = {}) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 32.dp).padding(top = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        action()
    }
}

/**
 * A quiet line explaining an empty section.
 *
 * @param text The line
 */
@Composable
private fun Quiet(text: String) {
    Text(text, style = BodyCompact, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/**
 * A white card holding rows separated by inset dividers.
 *
 * @param content The rows
 */
@Composable
private fun RowCard(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium),
        content = content,
    )
}

/**
 * A 72dp row inside a [RowCard].
 *
 * @param modifier The layout modifier
 * @param content The row's contents
 */
@Composable
private fun ListRow(modifier: Modifier = Modifier, content: @Composable RowScope.() -> Unit) {
    Row(
        modifier
            .fillMaxWidth()
            .heightIn(min = 72.dp)
            .padding(start = 16.dp, end = 12.dp, top = 10.dp, bottom = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        content = content,
    )
}

/** The divider between rows, inset from the left as the boards draw it. */
@Composable
private fun Divider() {
    HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.surfaceContainerHigh)
}

/** The partial-payment ink, for "of ৳1,200" on a short claim. */
private val PartialInk = Color(0xFF663C00)
