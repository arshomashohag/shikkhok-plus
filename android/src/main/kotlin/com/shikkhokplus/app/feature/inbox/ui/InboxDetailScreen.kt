package com.shikkhokplus.app.feature.inbox.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dateTimeLabel
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.inbox.InboxContent
import com.shikkhokplus.app.feature.inbox.InboxDetail
import com.shikkhokplus.app.feature.inbox.InboxDetailUiState
import com.shikkhokplus.app.feature.inbox.PaymentOutcome

/** The notice that an item can no longer be shown. */
const val TAG_INBOX_UNAVAILABLE: String = "inbox_unavailable"

/** The line saying an exam was cancelled. */
const val TAG_INBOX_EXAM_CANCELLED: String = "inbox_exam_cancelled"

/**
 * One opened inbox item.
 *
 * The teacher's words are drawn exactly as typed; what a payment came
 * to is the server's decision, shown and not worked out.
 *
 * @param state What to render
 * @param onBack Called to return to the inbox
 * @param onRetry Called to read again after a failure
 * @param modifier The layout modifier
 */
@Composable
fun InboxDetailScreen(
    state: InboxDetailUiState,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.inbox_detail_title),
        modifier = modifier,
        onBack = onBack,
    ) {
        when (state) {
            InboxDetailUiState.Loading -> SkeletonList(modifier = Modifier.padding(top = 8.dp))
            InboxDetailUiState.Unavailable ->
                Text(
                    stringResource(R.string.inbox_item_unavailable),
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(top = 8.dp).testTag(TAG_INBOX_UNAVAILABLE),
                )
            is InboxDetailUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    modifier = Modifier.padding(top = 8.dp),
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) onRetry else null,
                )
            is InboxDetailUiState.Loaded -> Body(state.detail)
        }
    }
}

/**
 * The item's heading and its content.
 *
 * @param detail The item
 */
@Composable
private fun Body(detail: InboxDetail) {
    Column(
        Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            inboxTitle(detail.kind, detail.childName, detail.batchName),
            style = MaterialTheme.typography.titleMedium,
        )
        when (val content = detail.content) {
            is InboxContent.Notice -> NoticeBody(content)
            is InboxContent.Exam -> ExamBody(content)
            is InboxContent.Payment -> PaymentBody(content)
            is InboxContent.ClassChanged ->
                classLine(detail.kind, content.change)?.let {
                    Text(it, style = MaterialTheme.typography.bodyLarge)
                }
            null -> Unit
        }
    }
}

/**
 * A labelled line.
 *
 * @param label What the value is
 * @param value The value, drawn as given
 */
@Composable
private fun Field(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyLarge)
    }
}

/**
 * A notice: the teacher's words, then when they were posted.
 *
 * @param notice The notice
 */
@Composable
private fun NoticeBody(notice: InboxContent.Notice) {
    Text(notice.body, style = MaterialTheme.typography.bodyLarge)
    Text(
        dateTimeLabel(notice.postedAt),
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    notice.editedAt?.let {
        Text(
            stringResource(R.string.inbox_notice_edited, dateTimeLabel(it)),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * An exam: its fields, and its topics as a bulleted list.
 *
 * @param exam The exam
 */
@Composable
private fun ExamBody(exam: InboxContent.Exam) {
    Text(Numerals.freeText(exam.title), style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold))
    if (exam.cancelled) {
        Text(
            stringResource(R.string.inbox_exam_cancelled_line),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.error,
            modifier = Modifier.testTag(TAG_INBOX_EXAM_CANCELLED),
        )
    }
    Field(stringResource(R.string.inbox_exam_date), shortDate(exam.date))
    Field(stringResource(R.string.inbox_exam_subject), Numerals.freeText(exam.subjectName))
    Field(stringResource(R.string.inbox_exam_total), Numerals.count(exam.totalMarks))
    if (exam.topics.isNotEmpty()) {
        Text(
            stringResource(R.string.inbox_exam_topics),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        exam.topics.forEach { Text("• ${Numerals.freeText(it)}", style = MaterialTheme.typography.bodyLarge) }
    }
}

/**
 * A payment: what was claimed, how it was decided, and why.
 *
 * @param payment The payment
 */
@Composable
private fun PaymentBody(payment: InboxContent.Payment) {
    Field(stringResource(R.string.inbox_payment_period), monthName(payment.period, short = false))
    Field(stringResource(R.string.inbox_payment_claimed), Numerals.money(payment.claimed))
    payment.approved?.let { Field(stringResource(R.string.inbox_payment_approved_amount), Numerals.money(it)) }
    Field(
        stringResource(R.string.inbox_payment_outcome),
        stringResource(
            when (payment.outcome) {
                PaymentOutcome.APPROVED -> R.string.inbox_outcome_approved
                PaymentOutcome.PARTIAL -> R.string.inbox_outcome_partial
                PaymentOutcome.REJECTED -> R.string.inbox_outcome_rejected
                PaymentOutcome.PENDING -> R.string.inbox_outcome_pending
            },
        ),
    )
    payment.reason?.let { Field(stringResource(R.string.inbox_payment_reason), Numerals.freeText(it)) }
}
