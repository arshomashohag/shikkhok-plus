package com.shikkhokplus.app.feature.student.ui

import com.shikkhokplus.app.feature.student.TopicRow
import com.shikkhokplus.app.feature.student.NextClass
import com.shikkhokplus.app.feature.student.FeeLine
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.format.dayLabel
import com.shikkhokplus.app.core.designsystem.TextAction
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.Alignment
import androidx.compose.material3.HorizontalDivider
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.core.ui.scheduleSummary
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.ProgressRow
import com.shikkhokplus.app.feature.student.StudentBatchUiState
import com.shikkhokplus.app.feature.student.StudentBatchView

/** The loading placeholder. */
const val TAG_STUDENT_BATCH_LOADING: String = "student_batch_loading"

/** The next-class card. */
const val TAG_STUDENT_NEXT_CLASS: String = "student_next_class"

/** One result row, which opens its marksheet. */
const val TAG_STUDENT_RESULT: String = "student_result"

/** One topic row. */
const val TAG_STUDENT_TOPIC: String = "student_topic"

/** One notice. */
const val TAG_STUDENT_NOTICE: String = "student_notice"

/** The fee-history link. */
const val TAG_STUDENT_FEES: String = "student_fees"

/** The failure message. */
const val TAG_STUDENT_BATCH_ERROR: String = "student_batch_error"

/**
 * S2: one batch from the student's side.
 *
 * Next class, the latest fee, results, the latest notice and the
 * topics covered. Everything shown is what the server decided; the
 * screen formats and decides nothing [TC-9].
 *
 * @param state What to render
 * @param onBack Called to leave
 * @param onOpenExam Called with an exam id when a result is tapped
 * @param onOpenFees Called to open the fee history
 * @param onRetry Called when the student asks to try again
 * @param modifier The layout modifier
 * @param onPay Called to pay this batch's fee (S3)
 */
@Composable
fun StudentBatchScreen(
    state: StudentBatchUiState,
    onBack: () -> Unit,
    onOpenExam: (String) -> Unit,
    onOpenFees: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    onPay: () -> Unit = {},
) {
    val batch = (state as? StudentBatchUiState.Loaded)?.view?.batch
    ScreenScaffold(
        title = batch?.batchName?.let(Numerals::freeText) ?: stringResource(R.string.my_batches_title),
        subtitle = batch?.teacherName?.let(Numerals::freeText),
        modifier = modifier,
        onBack = onBack,
    ) {
        when (state) {
            StudentBatchUiState.Loading -> LogoLoader(Modifier.testTag(TAG_STUDENT_BATCH_LOADING))
            is StudentBatchUiState.Loaded -> BatchBody(state.view, onOpenExam, onOpenFees, onPay)
            is StudentBatchUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_STUDENT_BATCH_ERROR),
                )
                if (state.retryable) {
                    Button(onClick = onRetry) { Text(stringResource(R.string.roster_retry)) }
                }
            }
        }
    }
}

/**
 * The loaded batch, top to bottom as S2 orders it.
 *
 * @param view The batch
 * @param onOpenExam Called with an exam id
 * @param onOpenFees Called to open the fee history
 * @param onPay Called to pay this batch's fee
 */
@Composable
private fun BatchBody(
    view: StudentBatchView,
    onOpenExam: (String) -> Unit,
    onOpenFees: () -> Unit,
    onPay: () -> Unit,
) {
    val next = view.next
    if (next == null) {
        ShikkhokCard(Modifier.testTag(TAG_STUDENT_NEXT_CLASS)) {
            Text(stringResource(R.string.student_no_next_class), color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    } else {
        NextClassHero(
            next,
            thenLine(view.following),
            withEnd = true,
            modifier = Modifier.testTag(TAG_STUDENT_NEXT_CLASS),
        )
    }

    view.batch.fee?.let { fee -> FeeCard(fee, onOpenFees, onPay) }
        ?: TextButton(onClick = onOpenFees, modifier = Modifier.testTag(TAG_STUDENT_FEES)) {
            Text(stringResource(R.string.screen_title_fee_history))
        }

    Section(stringResource(R.string.student_results))
    if (view.results.isEmpty()) {
        Quiet(stringResource(R.string.student_results_empty))
    } else {
        RowsCard {
            view.results.asReversed().forEachIndexed { index, row ->
                if (index > 0) InsetDivider()
                ResultRow(row, onOpen = { onOpenExam(row.examId) })
            }
        }
    }

    view.upcomingExam?.let { exam ->
        Section(stringResource(R.string.student_coming_up))
        RowsCard {
            Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(
                        stringResource(
                            R.string.student_exam_out_of,
                            Numerals.freeText(exam.title),
                            Numerals.count(exam.totalMarks),
                        ),
                        style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
                    )
                    Quiet(Numerals.freeText(exam.subjectName))
                }
                Text(dayLabel(exam.date), style = Emphasis)
            }
        }
    }

    view.notices.firstOrNull()?.let { notice ->
        Section(stringResource(R.string.student_latest_notice))
        ShikkhokCard(Modifier.testTag(TAG_STUDENT_NOTICE)) {
            Text(Numerals.freeText(notice.body))
            Quiet(ago(notice.postedAt))
        }
    }

    Section(stringResource(R.string.student_topics))
    if (view.topics.isEmpty()) {
        Quiet(stringResource(R.string.student_topics_empty))
    } else {
        RowsCard {
            view.topics.forEachIndexed { index, topic ->
                if (index > 0) InsetDivider()
                TopicRowView(topic)
            }
        }
    }

    if (view.notices.size > 1) {
        Section(stringResource(R.string.student_all_notices))
        RowsCard {
            view.notices.drop(1).forEachIndexed { index, notice ->
                if (index > 0) InsetDivider()
                Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp)) {
                    Text(Numerals.freeText(notice.body))
                    Quiet(shortDate(notice.postedAt.take(DATE_LENGTH)))
                }
            }
        }
    }
}

/**
 * "Then Mon 19 Oct, Wed 21 Oct (moved to 6:00 pm)", or null with none.
 *
 * @param following The classes after the next
 * @return The line
 */
@Composable
private fun thenLine(following: List<NextClass>): String? {
    if (following.isEmpty()) return null
    val days =
        following.map { next ->
            if (next.moved) {
                stringResource(R.string.student_moved_to, dayLabel(next.date), displayTime(next.startTime))
            } else {
                dayLabel(next.date)
            }
        }
    return stringResource(R.string.student_then, days.joinToString(", "))
}

/**
 * "October fee · ৳1,200", when it was paid or is due, and its chip; a
 * pay action while it is owed and not being checked.
 *
 * @param fee The period
 * @param onOpen Called to open the fee history
 * @param onPay Called to pay it
 */
@Composable
private fun FeeCard(fee: FeeLine, onOpen: () -> Unit, onPay: () -> Unit) {
    ShikkhokCard(onClick = onOpen, modifier = Modifier.testTag(TAG_STUDENT_FEES)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                val month = monthName(fee.period, short = false)
                Text(
                    fee.charged?.let { stringResource(R.string.student_fee_month_amount, month, Numerals.money(it)) }
                        ?: stringResource(R.string.student_fee_month, month),
                    style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
                )
                Quiet(
                    fee.paidOn?.let { stringResource(R.string.student_paid_on, shortDate(it)) }
                        ?: stringResource(R.string.student_due_by, shortDate(fee.dueDate)),
                )
            }
            FeeChip(fee)
        }
        if (!fee.verifying && fee.statusKey in PAYABLE_KEYS) {
            TextAction(stringResource(R.string.student_pay_this), onPay, Modifier.testTag(TAG_STUDENT_PAY))
        }
    }
}

/**
 * One result: the exam, its subject and date and rank, and the mark.
 *
 * @param row The result
 * @param onOpen Called to open its marksheet
 */
@Composable
private fun ResultRow(row: ProgressRow, onOpen: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onOpen)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag(TAG_STUDENT_RESULT),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                Numerals.freeText(row.examTitle),
                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
            )
            val meta =
                listOfNotNull(row.subjectName?.let(Numerals::freeText), shortDate(row.dateLabel)).joinToString(" · ")
            val rank = row.rank
            val out = row.rankedOutOf
            Quiet(
                if (rank != null && out != null) {
                    stringResource(R.string.student_result_rank, meta, Numerals.count(rank), Numerals.count(out))
                } else {
                    meta
                },
            )
        }
        val marks = row.marks
        if (marks == null) {
            // No mark is not zero: an absence shows as one [BR6.6].
            Quiet(stringResource(MessageKeys.resolve(row.stateLabel)))
        } else {
            Text(
                buildAnnotatedString {
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold, fontSize = 22.sp)) {
                        append(Numerals.count(marks))
                    }
                    append(stringResource(R.string.student_out_of, Numerals.count(row.totalMarks)))
                },
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

/**
 * One topic: the date and weekday in a column, then what was covered.
 *
 * @param topic The class
 */
@Composable
private fun TopicRowView(topic: TopicRow) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp).testTag(TAG_STUDENT_TOPIC),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.width(52.dp)) {
            Text(shortDate(topic.date), style = Emphasis)
            Quiet(dayLabel(topic.date).substringBefore(" "))
        }
        Column(Modifier.weight(1f)) {
            Text(Numerals.freeText(topic.topic))
            topic.subjectName?.let { Quiet(Numerals.freeText(it)) }
        }
    }
}

/**
 * A section heading, 14/22 bold in the board's grey.
 *
 * @param text The heading
 */
@Composable
private fun Section(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(top = 6.dp),
    )
}

/**
 * A quiet secondary line.
 *
 * @param text The line
 */
@Composable
private fun Quiet(text: String) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/**
 * A white card holding rows.
 *
 * @param content The rows
 */
@Composable
private fun RowsCard(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium),
        content = content,
    )
}

/** The divider between rows, inset from the left as the boards draw it. */
@Composable
private fun InsetDivider() {
    HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.surfaceContainerHigh)
}

/** A short value set in semibold, as the boards' dates are. */
private val Emphasis
    @Composable get() = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold)

/** The statuses a student can pay toward, as the fee mapper names them. */
private val PAYABLE_KEYS = setOf("fees.status.unpaid", "fees.status.partly_paid")

/** The "Pay this fee" action. */
const val TAG_STUDENT_PAY: String = "student_pay"

/** `yyyy-MM-dd` out of a timestamp. */
private const val DATE_LENGTH = 10

