package com.shikkhokplus.app.feature.collections.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.ui.HistoryLineText
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.collections.BatchMonthUiState
import com.shikkhokplus.app.feature.collections.MonthFilter
import com.shikkhokplus.app.feature.collections.MonthSeat
import com.shikkhokplus.app.feature.collections.SeatKind

/** Stable test identifiers. Not user-visible text. */
const val TAG_BATCH_MONTH_LOADING: String = "batch_month_loading"

/** The error card. */
const val TAG_BATCH_MONTH_ERROR: String = "batch_month_error"

/** The month switcher's label. */
const val TAG_BATCH_MONTH_LABEL: String = "batch_month_label"

/** The previous-month control. */
const val TAG_BATCH_MONTH_PREVIOUS: String = "batch_month_previous"

/** The next-month control. */
const val TAG_BATCH_MONTH_NEXT: String = "batch_month_next"

/** One filter chip. */
const val TAG_BATCH_MONTH_FILTER: String = "batch_month_filter"

/** One seat row. */
const val TAG_BATCH_MONTH_SEAT: String = "batch_month_seat"

/** The collected-of-charged headline. */
const val TAG_BATCH_MONTH_HEADLINE: String = "batch_month_headline"

/**
 * What the controls of the batch-month screen do.
 *
 * @property onRetry Ask again after a failure
 * @property onPrevious Show the month before
 * @property onNext Show the month after
 * @property onFilter A filter chip was tapped
 * @property onOpenSeat A seat was tapped, with its name
 * @property onBack The back arrow
 */
data class BatchMonthActions(
    val onRetry: () -> Unit = {},
    val onPrevious: () -> Unit = {},
    val onNext: () -> Unit = {},
    val onFilter: (MonthFilter) -> Unit = {},
    val onOpenSeat: (MonthSeat) -> Unit = {},
    val onBack: (() -> Unit)? = null,
)

/**
 * M2: one batch in one month, by seat.
 *
 * The filter labels carry the server's counts. The rows under a filter
 * are the server-decided states grouped the way the server counted
 * them; nothing here adds up a count or an amount [TC-9, D-20].
 *
 * @param batchName The batch's name, shown under the title
 * @param state What to render
 * @param actions What the controls do
 * @param modifier Layout modifier
 */
@Composable
fun BatchMonthScreen(
    batchName: String,
    state: BatchMonthUiState,
    actions: BatchMonthActions,
    modifier: Modifier = Modifier,
) {
    ListScreenScaffold(
        title = stringResource(R.string.screen_title_batch_fees),
        subtitle = batchName,
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        when (state) {
            BatchMonthUiState.Loading ->
                SkeletonList(modifier = Modifier.padding(top = 8.dp).testTag(TAG_BATCH_MONTH_LOADING))
            is BatchMonthUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    modifier = Modifier.padding(top = 8.dp).testTag(TAG_BATCH_MONTH_ERROR),
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            is BatchMonthUiState.Loaded -> Month(state, actions)
        }
    }
}

@Composable
private fun Month(
    state: BatchMonthUiState.Loaded,
    actions: BatchMonthActions,
) {
    Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextAction(
                text = "‹ " + stringResource(R.string.batch_month_previous),
                onClick = actions.onPrevious,
                modifier = Modifier.testTag(TAG_BATCH_MONTH_PREVIOUS),
            )
            Text(
                monthName(state.period, short = false) + " " + state.period.take(YEAR_LENGTH),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.testTag(TAG_BATCH_MONTH_LABEL),
            )
            if (state.canGoNext) {
                TextAction(
                    text = stringResource(R.string.batch_month_next) + " ›",
                    onClick = actions.onNext,
                    modifier = Modifier.testTag(TAG_BATCH_MONTH_NEXT),
                )
            }
        }
        Column(Modifier.testTag(TAG_BATCH_MONTH_HEADLINE)) {
            Text(Numerals.money(state.collected), style = MaterialTheme.typography.headlineMedium)
            Text(
                stringResource(R.string.batch_month_collected_of, Numerals.money(state.charged)),
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        Filters(state, actions)
        if (state.seats.isEmpty()) {
            Text(stringResource(R.string.batch_month_no_seats))
        }
        state.seats.forEach { seat -> SeatRow(seat, actions.onOpenSeat) }
    }
}

private const val YEAR_LENGTH = 4

private fun Modifier.fillMaxWidth(): Modifier = this.then(Modifier.padding(0.dp))

@Composable
private fun Filters(
    state: BatchMonthUiState.Loaded,
    actions: BatchMonthActions,
) {
    val entries =
        listOf(
            MonthFilter.ALL to stringResource(R.string.batch_month_filter_all),
            MonthFilter.PAID to stringResource(R.string.batch_month_filter_paid, state.counts.paid),
            MonthFilter.CHECKING to stringResource(R.string.batch_month_filter_checking, state.counts.checking),
            MonthFilter.OWED to stringResource(R.string.batch_month_filter_owed, state.counts.owed),
        )
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        items(entries, key = { it.first }) { (filter, label) ->
            FilterPill(label, state.filter == filter, { actions.onFilter(filter) }, TAG_BATCH_MONTH_FILTER)
        }
    }
}

@Composable
private fun SeatRow(
    seat: MonthSeat,
    onOpen: (MonthSeat) -> Unit,
) {
    ShikkhokCard(Modifier.testTag(TAG_BATCH_MONTH_SEAT), onClick = { onOpen(seat) }) {
        Row(
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(seat.displayName, style = MaterialTheme.typography.titleSmall)
            SeatChip(seat.kind)
        }
        seatDetail(seat)?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
        seat.historyLine?.let { HistoryLineText(it) }
    }
}

@Composable
private fun seatDetail(seat: MonthSeat): String? =
    when (seat.kind) {
        SeatKind.DUE, SeatKind.PARTIAL ->
            stringResource(R.string.batch_month_owed, Numerals.money(seat.outstanding))
        SeatKind.OVERDUE ->
            seat.daysOverdue?.let {
                stringResource(R.string.batch_month_owed_late, Numerals.money(seat.outstanding), it)
            } ?: stringResource(R.string.batch_month_owed, Numerals.money(seat.outstanding))
        SeatKind.CHECKING ->
            seat.verifying?.let { stringResource(R.string.batch_month_sending, Numerals.money(it)) }
        SeatKind.PAID, SeatKind.WAIVED, SeatKind.NONE -> null
    }

@Composable
private fun SeatChip(kind: SeatKind) {
    when (kind) {
        SeatKind.PAID -> PaymentStateChip(PaymentState.PAID, stringResource(R.string.student_chip_paid), compact = true)
        SeatKind.WAIVED ->
            PaymentStateChip(PaymentState.PAID, stringResource(R.string.student_chip_waived), compact = true)
        SeatKind.PARTIAL ->
            PaymentStateChip(PaymentState.PARTIAL, stringResource(R.string.student_chip_partly_paid), compact = true)
        SeatKind.DUE ->
            PaymentStateChip(PaymentState.DUE, stringResource(R.string.batch_month_chip_due), compact = true)
        SeatKind.OVERDUE ->
            PaymentStateChip(PaymentState.OVERDUE, stringResource(R.string.batch_month_chip_overdue), compact = true)
        SeatKind.CHECKING ->
            PaymentStateChip(PaymentState.VERIFYING, stringResource(R.string.student_chip_verifying), compact = true)
        SeatKind.NONE ->
            Text(stringResource(R.string.batch_month_chip_none), style = MaterialTheme.typography.labelMedium)
    }
}
