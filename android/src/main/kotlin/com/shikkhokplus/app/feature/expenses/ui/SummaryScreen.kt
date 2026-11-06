package com.shikkhokplus.app.feature.expenses.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.expenses.MoneySummary
import com.shikkhokplus.app.feature.expenses.NetKind
import com.shikkhokplus.app.feature.expenses.SummaryBody
import com.shikkhokplus.app.feature.expenses.SummaryUiState

/** The headline card: collected, spent and the verdict. */
const val TAG_SUMMARY_HEADLINE: String = "summary_headline"

/**
 * Tag for one extra fee's line.
 *
 * @param extraFeeId The fee
 * @return The tag
 */
fun summaryFeeTag(extraFeeId: String): String = "summary_fee_$extraFeeId"

/**
 * Where the summary leads.
 *
 * @property onShift Moves the month by -1 or 1
 * @property onRetry Reads again after a failure
 * @property onOpenExpenses Opens the expense list
 * @property onBack Leaves the screen
 */
data class SummaryActions(
    val onShift: (Long) -> Unit = {},
    val onRetry: () -> Unit = {},
    val onOpenExpenses: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The month's money in and out, what is still owed today, and each extra
 * fee's takings against its spending. Every figure and the surplus-or-
 * deficit verdict are the server's.
 *
 * @param state What to render
 * @param actions Where each control leads
 * @param modifier Layout modifier from the caller
 */
@Composable
fun SummaryScreen(
    state: SummaryUiState,
    actions: SummaryActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.summary_title),
        subtitle = stringResource(R.string.summary_basis),
        modifier = modifier,
        onBack = actions.onBack,
        actions = { TextAction(stringResource(R.string.money_open_expenses), actions.onOpenExpenses) },
    ) {
        MonthBar(state.month, state.canGoForward, actions.onShift)
        when (val body = state.body) {
            SummaryBody.Loading -> SkeletonList(rows = 4)
            is SummaryBody.Loaded -> SummaryContent(body.summary)
            is SummaryBody.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = null,
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) actions.onRetry else null,
                )
        }
    }
}

@Composable
private fun SummaryContent(summary: MoneySummary) {
    val verdict =
        when (summary.netKind) {
            NetKind.SURPLUS -> R.string.summary_surplus
            NetKind.DEFICIT -> R.string.summary_deficit
            NetKind.EVEN -> R.string.summary_even
        }
    Column(Modifier.testTag(TAG_SUMMARY_HEADLINE)) {
        MoneyLines(
            title = null,
            lines =
                listOf(
                    stringResource(R.string.summary_collected) to summary.collectedTotal,
                    stringResource(R.string.summary_spent) to summary.spentTotal,
                ),
            total = stringResource(verdict) to summary.net,
        )
    }
    MoneyLines(
        title = stringResource(R.string.summary_collected),
        lines =
            listOf(
                stringResource(R.string.summary_monthly) to summary.collectedMonthly,
                stringResource(R.string.summary_exam) to summary.collectedExam,
                stringResource(R.string.summary_other) to summary.collectedOther,
            ),
    )
    if (summary.spentByCategory.isNotEmpty()) {
        CategoryLines(stringResource(R.string.summary_spent), summary.spentByCategory)
    }
    MoneyLines(
        title = stringResource(R.string.summary_owed_today),
        lines =
            listOf(
                stringResource(R.string.summary_owed_monthly) to summary.owedMonthly,
                stringResource(R.string.summary_owed_extra) to summary.owedExtra,
            ),
    )
    if (summary.fees.isNotEmpty()) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                text = stringResource(R.string.summary_per_fee),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.asHeading(),
            )
            summary.fees.forEach { fee ->
                ShikkhokCard(modifier = Modifier.testTag(summaryFeeTag(fee.extraFeeId))) {
                    Text(fee.label, style = MaterialTheme.typography.titleMedium)
                    Text(
                        text =
                            stringResource(
                                R.string.summary_fee_line,
                                Numerals.money(fee.collected),
                                Numerals.money(fee.spent),
                            ),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}
