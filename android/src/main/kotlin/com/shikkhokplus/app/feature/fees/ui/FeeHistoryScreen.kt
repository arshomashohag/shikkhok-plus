package com.shikkhokplus.app.feature.fees.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.ui.HistoryLineText
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.fees.FeeCycleRow
import com.shikkhokplus.app.feature.fees.FeeUiState
import com.shikkhokplus.app.feature.fees.MonthStateRow
import com.shikkhokplus.app.feature.fees.StripKind

/** Stable test identifiers. Not user-visible text. */
const val TAG_FEES_LOADING: String = "fees_loading"

/** The explanation shown when no period has generated yet. */
const val TAG_FEES_EMPTY: String = "fees_empty"

/** The list of periods. */
const val TAG_FEES_LIST: String = "fees_list"

/** One period. */
const val TAG_FEES_ROW: String = "fees_row"

/** The total owed across every period, as the server computed it. */
const val TAG_FEES_TOTAL: String = "fees_total"

/** One period's server-decided status. */
const val TAG_FEES_STATUS: String = "fees_status"

/** One period's outstanding amount. */
const val TAG_FEES_OUTSTANDING: String = "fees_outstanding"

/** The 6-month strip. */
const val TAG_FEES_STRIP: String = "fees_strip"

/** One month on the strip. */
const val TAG_FEES_STRIP_CELL: String = "fees_strip_cell"

/** A month's latest claim, worded from structured fields. */
const val TAG_FEES_HISTORY_LINE: String = "fees_history_line"

/** The error message. */
const val TAG_FEES_ERROR: String = "fees_error"

/** The link to this seat's progress dashboard. */
const val TAG_FEES_PROGRESS: String = "fees_progress"

/** The retry button, shown only when the server said retryable. */
const val TAG_FEES_RETRY: String = "fees_retry"

/**
 * A student's or guardian's own fee history.
 *
 * **This composable renders a [FeeUiState] and nothing else.** There is
 * no conditional here depending on a domain value — in particular, **no
 * comparison of an amount against zero to decide a label or a colour**.
 * `if (balance > 0) "Due" else "Paid"` is a business rule about what
 * counts as due written where it looks like presentation, and it is
 * wrong for a waived cycle: the balance is zero and nobody paid
 * [BR6.1, TC-9, D-31].
 *
 * The team practice names this screen and D5's dues list as the two
 * places that boundary is tested hardest in the product, so the row
 * carries `statusLabel` and `isSettled` as **fields the mapper
 * decided**, and this file reads them.
 *
 * Amounts are rendered through [Numerals], which emits Latin digits
 * under every locale — agreeing with the server's `Money.format`
 * rather than deciding independently [BR6.6].
 *
 * @param state What to render
 * @param onRetry Called when the viewer asks to retry
 * @param onBack Called by the back arrow
 * @param modifier Layout modifier
 * @param onOpenProgress Opens this seat's progress dashboard, or null
 *   where the reader has no such link here
 */
@Composable
fun FeeHistoryScreen(
    state: FeeUiState,
    onRetry: () -> Unit,
    onBack: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
    onOpenProgress: (() -> Unit)? = null,
) {
    ListScreenScaffold(
        title = stringResource(R.string.screen_title_fee_history),
        onBack = onBack,
        modifier = modifier,
        header = {
            if (onOpenProgress != null && state !is FeeUiState.Loading) {
                TextAction(
                    text = stringResource(R.string.dashboard_open_progress),
                    onClick = onOpenProgress,
                    modifier = Modifier.testTag(TAG_FEES_PROGRESS),
                )
            }
        },
    ) {
        when (state) {
            FeeUiState.Loading ->
                LogoLoader(Modifier.testTag(TAG_FEES_LOADING))

            FeeUiState.Empty ->
                // Nothing CHARGED yet is not the same as everything
                // paid, and a blank list explains neither.
                Text(
                    stringResource(R.string.fees_empty),
                    Modifier.testTag(TAG_FEES_EMPTY),
                )

            is FeeUiState.Loaded -> {
                Text(
                    stringResource(
                        R.string.fees_total_outstanding,
                        Numerals.money(state.totalOutstanding),
                    ),
                    modifier = Modifier.testTag(TAG_FEES_TOTAL),
                    style = MaterialTheme.typography.titleMedium,
                )
                LazyColumn(
                    modifier = Modifier.testTag(TAG_FEES_LIST),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    if (state.months.isNotEmpty()) {
                        item(key = "strip") { MonthStrip(state.months) }
                    }
                    items(state.rows, key = { it.period }) { row ->
                        FeePeriodRow(row, state.months.firstOrNull { it.period == row.period })
                    }
                }
            }

            is FeeUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_FEES_ERROR),
                )
                // The server says whether retrying could help; the
                // client never infers it from a status code.
                if (state.retryable) {
                    TextButton(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_FEES_RETRY),
                    ) {
                        Text(stringResource(R.string.roster_retry))
                    }
                }
            }
        }
    }
}

/**
 * One period.
 *
 * Renders the status enum through the key the mapper chose. **There is
 * no `if` over `row.outstanding` here**: the settled distinction is
 * `row.isSettled`, which the mapper derived from the server's status
 * rather than from the amount, so a waived cycle is not drawn as paid.
 *
 * @param row The period to render
 * @param month The strip entry for the same month, whose claim is shown
 */
@Composable
private fun FeePeriodRow(
    row: FeeCycleRow,
    month: MonthStateRow?,
) {
    Column(
        modifier = Modifier.fillMaxWidth().testTag(TAG_FEES_ROW),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(row.periodLabel, style = MaterialTheme.typography.titleSmall)
        Text(
            stringResource(MessageKeys.resolve(row.statusLabel)),
            modifier = Modifier.testTag(TAG_FEES_STATUS),
            color =
                if (row.isSettled) {
                    MaterialTheme.colorScheme.onSurfaceVariant
                } else {
                    MaterialTheme.colorScheme.error
                },
        )
        Text(
            stringResource(
                R.string.fees_outstanding_of_charged,
                Numerals.money(row.outstanding),
                Numerals.money(row.charged),
            ),
            modifier = Modifier.testTag(TAG_FEES_OUTSTANDING),
        )
        Text(
            stringResource(R.string.fees_due_on, row.dueDateLabel),
            style = MaterialTheme.typography.bodySmall,
        )
        month?.historyLine?.let { HistoryLineText(it, Modifier.testTag(TAG_FEES_HISTORY_LINE)) }
    }
}

/**
 * The last months at a glance: one glyph per month, from the server's
 * state, with a legend. Nothing here compares an amount.
 *
 * @param months The strip, oldest first
 */
@Composable
private fun MonthStrip(months: List<MonthStateRow>) {
    Column(Modifier.testTag(TAG_FEES_STRIP), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(stringResource(R.string.fee_strip_title), style = MaterialTheme.typography.titleSmall)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            months.forEach { month ->
                val name = monthName(month.period)
                val description = stringResource(R.string.fee_strip_cell_desc, name, stateWord(month.kind))
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier =
                        Modifier
                            .testTag(TAG_FEES_STRIP_CELL)
                            .semantics(mergeDescendants = true) {
                                contentDescription = description
                            },
                ) {
                    Text(glyph(month.kind), style = MaterialTheme.typography.titleMedium)
                    Text(name, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
        Text(
            stringResource(R.string.fee_strip_legend),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
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
