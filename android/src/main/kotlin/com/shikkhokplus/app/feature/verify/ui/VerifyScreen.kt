package com.shikkhokplus.app.feature.verify.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.StateFade
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.verify.Comparison
import com.shikkhokplus.app.feature.verify.RecentRow
import com.shikkhokplus.app.feature.verify.ReviewCard
import com.shikkhokplus.app.feature.verify.VerifyUiState

/** One payment row in the queue. */
const val TAG_VERIFY_CARD: String = "verify_card"

/** The empty state. */
const val TAG_VERIFY_ALL_CAUGHT_UP: String = "verify_all_caught_up"

/**
 * R1: payments waiting for the teacher to check.
 *
 * Every amount and comparison is the server's; a row names them and
 * opens the payment [TC-9].
 *
 * @param state What to render
 * @param onBack Called to leave
 * @param onOpen Called with the payment to review
 * @param onRetry Called to read the queue again
 * @param modifier The layout modifier
 */
@Composable
fun VerifyScreen(
    state: VerifyUiState,
    onBack: () -> Unit,
    onOpen: (String) -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    refreshing: Boolean = false,
    onRefresh: (() -> Unit)? = null,
) {
    ListScreenScaffold(
        title = stringResource(R.string.verify_title),
        subtitle = subtitleOf(state),
        onBack = onBack,
        modifier = modifier,
        refreshing = refreshing,
        onRefresh = onRefresh,
    ) {
        StateFade(state, spacing = Spacing.tight, modifier = Modifier.fillMaxSize()) { shown ->
            when (shown) {
                VerifyUiState.Loading -> SkeletonList(rows = 3)

                is VerifyUiState.Waiting ->
                    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        items(shown.pending, key = { it.submissionId }) { card ->
                            // Keyed rows animate when the queue changes in
                            // place — a pull that finds a new payment, or
                            // one already decided dropping out — so the
                            // teacher sees what changed rather than a list
                            // that silently became a different list.
                            QueueRow(card, Modifier.animateItem()) { onOpen(card.submissionId) }
                        }
                        if (shown.recent.isNotEmpty()) item { RecentList(shown.recent, onOpen) }
                    }

                // Scrollable so a pull works here: "all caught up" is the
                // state a teacher waiting for a payment pulls on.
                is VerifyUiState.AllCaughtUp ->
                    Column(
                        Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        EmptyState(
                            title = stringResource(R.string.verify_all_caught_up),
                            body = stringResource(R.string.verify_all_caught_up_body),
                            modifier = Modifier.testTag(TAG_VERIFY_ALL_CAUGHT_UP),
                        )
                        if (shown.recent.isNotEmpty()) RecentList(shown.recent, onOpen)
                    }

                is VerifyUiState.Failed ->
                    ErrorCard(
                        title = stringResource(R.string.verify_load_failed),
                        body = stringResource(MessageKeys.resolve(shown.messageKey)),
                        retryLabel = stringResource(R.string.roster_retry).takeIf { shown.retryable },
                        onRetry = onRetry.takeIf { shown.retryable },
                    )
            }
        }
    }
}

/**
 * The bar's subtitle: how many wait, or that nothing does.
 *
 * @param state The screen state
 * @return The subtitle, or null while loading
 */
@Composable
private fun subtitleOf(state: VerifyUiState): String? =
    when (state) {
        is VerifyUiState.Waiting -> stringResource(R.string.verify_waiting, Numerals.count(state.pending.size))
        is VerifyUiState.AllCaughtUp -> stringResource(R.string.verify_nothing_waiting)
        VerifyUiState.Loading -> stringResource(R.string.verify_checking)
        is VerifyUiState.Failed -> null
    }

/**
 * One waiting payment: who, how much, and how it compares.
 *
 * @param card The payment
 * @param modifier Carries the list's item animation
 * @param onClick Called to open it
 */
@Composable
private fun QueueRow(card: ReviewCard, modifier: Modifier = Modifier, onClick: () -> Unit) {
    ShikkhokCard(modifier.testTag(TAG_VERIFY_CARD).clickable(onClick = onClick)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Initial(card.displayName)
            Column(Modifier.weight(1f)) {
                Text(Numerals.freeText(card.displayName), style = MaterialTheme.typography.titleMedium)
                Text(
                    "${Numerals.freeText(card.batchName)} · ${ago(card.submittedAt)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(Numerals.money(card.totalAmount), style = MaterialTheme.typography.titleMedium)
        }
        ComparisonChip(card)
    }
}

/**
 * The server's comparison as a chip: matches, short or over.
 *
 * @param card The payment
 */
@Composable
internal fun ComparisonChip(card: ReviewCard) {
    when (card.comparison) {
        Comparison.MATCHES ->
            PaymentStateChip(
                PaymentState.PAID,
                stringResource(R.string.verify_matches, monthName(card.period)),
                compact = true,
            )
        Comparison.SHORT ->
            PaymentStateChip(
                PaymentState.PARTIAL,
                stringResource(
                    R.string.verify_short,
                    Numerals.money(card.difference),
                    Numerals.money(card.owedTogether),
                ),
                compact = true,
            )
        Comparison.OVER ->
            PaymentStateChip(
                PaymentState.DUE,
                stringResource(
                    R.string.verify_over,
                    Numerals.money(card.difference),
                    Numerals.money(card.owedTogether),
                ),
                compact = true,
            )
    }
}

/**
 * A 40dp circle with a name's first letter.
 *
 * @param name The name
 */
@Composable
private fun Initial(name: String) {
    Box(
        Modifier.size(40.dp).background(MaterialTheme.colorScheme.surfaceContainerHigh, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            name.trim().take(1),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * The last day's decisions, under a heading.
 *
 * @param rows The decisions, newest first
 * @param onOpen Called with a decided payment to look at again
 */
@Composable
private fun RecentList(rows: List<RecentRow>, onOpen: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.verify_decided_today), style = MaterialTheme.typography.titleSmall)
        ShikkhokCard {
            rows.forEach { row ->
                Row(
                    Modifier.fillMaxWidth().clickable { onOpen(row.submissionId) },
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(Numerals.freeText(row.displayName), style = MaterialTheme.typography.titleMedium)
                        Text(
                            Numerals.freeText(row.batchName),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Text(Numerals.money(row.amount), style = MaterialTheme.typography.titleMedium)
                    PaymentStateChip(
                        if (row.statusKey == "verify.decision.approved") PaymentState.PAID else PaymentState.DUE,
                        stringResource(decisionLabel(row.statusKey)),
                        compact = true,
                    )
                }
            }
        }
    }
}

/**
 * The label for a payment decision.
 *
 * @param key The decision's key from the mapper
 * @return Its string resource
 */
internal fun decisionLabel(key: String): Int =
    when (key) {
        "verify.decision.approved" -> R.string.verify_decision_approved
        "verify.decision.rejected" -> R.string.verify_decision_rejected
        else -> R.string.verify_decision_pending
    }
