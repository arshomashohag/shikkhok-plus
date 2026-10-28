package com.shikkhokplus.app.feature.guardian.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.feature.guardian.LineState
import com.shikkhokplus.app.feature.guardian.PaymentLine
import com.shikkhokplus.app.feature.guardian.PaymentsUiState
import com.shikkhokplus.app.feature.pay.PayOption

/** One month's line. */
const val TAG_PAYMENT_LINE: String = "payment_line"

/** The pay button under the history. */
const val TAG_PAYMENTS_PAY: String = "payments_pay"

/** The "couldn't load" card, which warns against paying again. */
const val TAG_PAYMENTS_ERROR: String = "payments_error"

/**
 * G3: one child's payments, newest month first, with this year's total.
 *
 * **A failed read says not to pay again** until it loads: an earlier
 * payment may already be recorded, and paying blind is how a guardian
 * pays twice.
 *
 * @param state What to render
 * @param onBack Called to leave
 * @param onPay Called to pay the offered fee
 * @param onRetry Called to read again
 */
@Composable
fun PaymentsScreen(state: PaymentsUiState, onBack: () -> Unit, onPay: (PayOption) -> Unit, onRetry: () -> Unit) {
    val loaded = state as? PaymentsUiState.Loaded
    ScreenScaffold(
        title =
            loaded?.let { stringResource(R.string.payments_title, Numerals.freeText(firstName(it.childName))) }
                ?: stringResource(R.string.guardian_open_fees),
        onBack = onBack,
        bottomBar = {
            loaded?.next?.let { next ->
                Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)) {
                    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
                    PrimaryButton(
                        text =
                            stringResource(
                                R.string.payments_pay_for,
                                Numerals.money(next.amountDue),
                                Numerals.freeText(next.batchName),
                            ),
                        onClick = { onPay(next) },
                        modifier = Modifier.fillMaxWidth().padding(16.dp).testTag(TAG_PAYMENTS_PAY),
                    )
                }
            }
        },
    ) {
        when (state) {
            PaymentsUiState.Loading -> SkeletonList()
            is PaymentsUiState.Failed ->
                ErrorCard(
                    title = stringResource(R.string.payments_error_title),
                    body = stringResource(R.string.payments_error_body),
                    modifier = Modifier.testTag(TAG_PAYMENTS_ERROR),
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) onRetry else null,
                )
            is PaymentsUiState.Loaded -> History(state)
        }
    }
}

/**
 * The year's total, then each month's lines.
 *
 * @param state The history
 */
@Composable
private fun History(state: PaymentsUiState.Loaded) {
    if (state.months.isEmpty()) {
        EmptyState(
            title = stringResource(R.string.payments_empty_title),
            body = stringResource(R.string.payments_empty_body, Numerals.freeText(firstName(state.childName))),
        )
        return
    }
    Text(
        stringResource(R.string.payments_paid_in, Numerals.count(state.year), Numerals.money(state.paidThisYear)),
        style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
    )
    state.months.forEach { month ->
        Text(
            "${monthName(month.period, short = false)} ${month.period.take(YEAR_LENGTH)}",
            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 6.dp),
        )
        Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)) {
            month.lines.forEachIndexed { index, line ->
                if (index > 0) {
                    HorizontalDivider(
                        Modifier.padding(start = 16.dp),
                        color = MaterialTheme.colorScheme.surfaceContainerHigh,
                    )
                }
                LineRow(line)
            }
        }
    }
}

/**
 * One batch's month: name, where its payment stands, amount and chip.
 *
 * @param line The line
 */
@Composable
private fun LineRow(line: PaymentLine) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag(TAG_PAYMENT_LINE),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(Numerals.freeText(line.batchName), style = MaterialTheme.typography.titleMedium)
            Text(
                statusLine(line),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                Numerals.money(line.amount),
                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold),
            )
            val (state, label) = chipOf(line.state)
            PaymentStateChip(state, stringResource(label), compact = true)
        }
    }
}

/**
 * "Due by 20 Oct", "You sent it 15 Oct · Nagad" or "Approved 8 Oct · bKash".
 *
 * @param line The line
 * @return The status line
 */
@Composable
private fun statusLine(line: PaymentLine): String {
    val sent = line.sentOn
    val decided = line.decidedOn
    val channel = line.channel.orEmpty()
    return when {
        line.state == LineState.VERIFYING && sent != null ->
            stringResource(R.string.payments_you_sent, shortDate(sent), channel)
        decided != null -> stringResource(R.string.payments_approved, shortDate(decided), channel)
        line.state == LineState.WAIVED -> stringResource(R.string.student_chip_waived)
        else -> stringResource(R.string.student_due_by, shortDate(line.dueDate))
    }
}

/**
 * A line's chip.
 *
 * @param state The line's state
 * @return The chip state and its label
 */
private fun chipOf(state: LineState): Pair<PaymentState, Int> =
    when (state) {
        LineState.PAID -> PaymentState.PAID to R.string.student_chip_paid
        LineState.WAIVED -> PaymentState.PAID to R.string.student_chip_waived
        LineState.PARTLY_PAID -> PaymentState.PARTIAL to R.string.student_chip_partly_paid
        LineState.VERIFYING -> PaymentState.VERIFYING to R.string.student_chip_verifying
        LineState.DUE -> PaymentState.DUE to R.string.payments_due
    }

/** `YYYY` out of `YYYY-MM`. */
private const val YEAR_LENGTH = 4
