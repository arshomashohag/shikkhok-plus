package com.shikkhokplus.app.feature.verify.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.DestructiveButton
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TonalButton
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.verify.ClaimCard
import com.shikkhokplus.app.feature.verify.Comparison
import com.shikkhokplus.app.feature.verify.PartialSheet
import com.shikkhokplus.app.feature.verify.RecentRow
import com.shikkhokplus.app.feature.verify.VerifyUiState

/** One claim card. */
const val TAG_VERIFY_CARD: String = "verify_card"

/** A card's approve button. */
const val TAG_VERIFY_APPROVE: String = "verify_approve"

/** A card's partial button. */
const val TAG_VERIFY_PARTIAL: String = "verify_partial"

/** A card's reject button. */
const val TAG_VERIFY_REJECT: String = "verify_reject"

/** The reject confirmation's confirm button. */
const val TAG_VERIFY_REJECT_CONFIRM: String = "verify_reject_confirm"

/** The duplicate-reference warning. */
const val TAG_VERIFY_DUPLICATE: String = "verify_duplicate"

/** The empty state. */
const val TAG_VERIFY_ALL_CAUGHT_UP: String = "verify_all_caught_up"

/** A refused decision, shown above the list. */
const val TAG_VERIFY_ERROR: String = "verify_error"

/**
 * T4: payments waiting for the teacher to check.
 *
 * Every amount and comparison on a card is the server's; the screen
 * names them and decides nothing [TC-9].
 *
 * @param state What to render
 * @param sheet The partial-approval sheet, while open
 * @param onBack Called to leave
 * @param onApprove Called with a claim to approve as sent
 * @param onPartial Called with a claim to approve in part
 * @param onReject Called with a claim the teacher confirmed rejecting
 * @param onRetry Called to read the queue again
 * @param onTypePartial Called with the partial amount as typed
 * @param onChoose Called with `carried` or `waived`
 * @param onConfirmPartial Called to approve the partial amount
 * @param onClosePartial Called to close the sheet
 * @param modifier The layout modifier
 */
@Composable
fun VerifyScreen(
    state: VerifyUiState,
    sheet: PartialSheet?,
    onBack: () -> Unit,
    onApprove: (ClaimCard) -> Unit,
    onPartial: (ClaimCard) -> Unit,
    onReject: (ClaimCard) -> Unit,
    onRetry: () -> Unit,
    onTypePartial: (String) -> Unit,
    onChoose: (String) -> Unit,
    onConfirmPartial: () -> Unit,
    onClosePartial: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var rejecting by remember { mutableStateOf<ClaimCard?>(null) }

    ListScreenScaffold(
        title = stringResource(R.string.verify_title),
        subtitle = subtitleOf(state),
        onBack = onBack,
        modifier = modifier,
    ) {
        when (state) {
            VerifyUiState.Loading -> SkeletonList(rows = 3)

            is VerifyUiState.Waiting ->
                LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    state.errorKey?.let { key ->
                        item {
                            Banner(
                                title = stringResource(MessageKeys.resolve(key)),
                                tone = BannerTone.ERROR,
                                modifier = Modifier.testTag(TAG_VERIFY_ERROR),
                            )
                        }
                    }
                    items(state.pending, key = { it.claimId }) { card ->
                        ClaimCardView(
                            card = card,
                            busy = state.busyClaimId != null,
                            onApprove = { onApprove(card) },
                            onPartial = { onPartial(card) },
                            onReject = { rejecting = card },
                        )
                    }
                    if (state.recent.isNotEmpty()) item { RecentList(state.recent) }
                }

            is VerifyUiState.AllCaughtUp ->
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    EmptyState(
                        title = stringResource(R.string.verify_all_caught_up),
                        body = stringResource(R.string.verify_all_caught_up_body),
                        modifier = Modifier.testTag(TAG_VERIFY_ALL_CAUGHT_UP),
                    )
                    if (state.recent.isNotEmpty()) RecentList(state.recent)
                }

            is VerifyUiState.Failed ->
                ErrorCard(
                    title = stringResource(R.string.verify_load_failed),
                    body = stringResource(MessageKeys.resolve(state.messageKey)),
                    retryLabel = stringResource(R.string.roster_retry).takeIf { state.retryable },
                    onRetry = onRetry.takeIf { state.retryable },
                )
        }
    }

    rejecting?.let { card ->
        AlertDialog(
            onDismissRequest = { rejecting = null },
            title = { Text(stringResource(R.string.verify_reject_title)) },
            text = {
                Text(
                    stringResource(
                        R.string.verify_reject_body,
                        Numerals.freeText(card.displayName),
                        Numerals.money(card.claimedAmount),
                    ),
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        rejecting = null
                        onReject(card)
                    },
                    modifier = Modifier.testTag(TAG_VERIFY_REJECT_CONFIRM),
                ) { Text(stringResource(R.string.verify_reject), color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { rejecting = null }) { Text(stringResource(R.string.action_cancel)) }
            },
        )
    }

    sheet?.let {
        PartialApprovalSheet(
            sheet = it,
            onType = onTypePartial,
            onChoose = onChoose,
            onConfirm = onConfirmPartial,
            onDismiss = onClosePartial,
        )
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
 * One claim: who, how much, how it compares, the reference and the actions.
 *
 * @param card The claim
 * @param busy Whether a decision is being sent, which disables actions
 * @param onApprove Called to approve
 * @param onPartial Called to approve in part
 * @param onReject Called to ask to reject
 */
@Composable
private fun ClaimCardView(
    card: ClaimCard,
    busy: Boolean,
    onApprove: () -> Unit,
    onPartial: () -> Unit,
    onReject: () -> Unit,
) {
    ShikkhokCard(Modifier.testTag(TAG_VERIFY_CARD)) {
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
        }
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(Numerals.money(card.claimedAmount), style = MaterialTheme.typography.headlineMedium)
            ComparisonChip(card)
        }
        Details(card)
        card.duplicate?.let { duplicate ->
            Banner(
                title = stringResource(R.string.verify_duplicate_title),
                body =
                    stringResource(
                        R.string.verify_duplicate_body,
                        Numerals.freeText(duplicate.displayName),
                        stringResource(decisionLabel(duplicate.statusKey)),
                        Numerals.money(duplicate.amount),
                    ),
                tone = BannerTone.ERROR,
                modifier = Modifier.testTag(TAG_VERIFY_DUPLICATE),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DestructiveButton(
                text = stringResource(R.string.verify_reject),
                onClick = onReject,
                enabled = !busy,
                modifier = Modifier.testTag(TAG_VERIFY_REJECT),
            )
            if (card.comparison != Comparison.SHORT) {
                TonalButton(
                    text = stringResource(R.string.verify_partial),
                    onClick = onPartial,
                    enabled = !busy,
                    modifier = Modifier.testTag(TAG_VERIFY_PARTIAL),
                )
            }
            PrimaryButton(
                text =
                    if (card.comparison == Comparison.SHORT) {
                        stringResource(R.string.verify_approve_amount, Numerals.money(card.claimedAmount))
                    } else {
                        stringResource(R.string.verify_approve)
                    },
                onClick = onApprove,
                enabled = !busy,
                compact = true,
                modifier = Modifier.weight(1f).testTag(TAG_VERIFY_APPROVE),
            )
        }
    }
}

/**
 * The server's comparison as a chip: matches, short or over.
 *
 * @param card The claim
 */
@Composable
private fun ComparisonChip(card: ClaimCard) {
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
                stringResource(R.string.verify_short, Numerals.money(card.difference), Numerals.money(card.charged)),
                compact = true,
            )
        Comparison.OVER ->
            PaymentStateChip(
                PaymentState.DUE,
                stringResource(R.string.verify_over, Numerals.money(card.difference), Numerals.money(card.charged)),
                compact = true,
            )
    }
}

/**
 * The reference and the sender, as label and value rows.
 *
 * @param card The claim
 */
@Composable
private fun Details(card: ClaimCard) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        card.transactionId?.let { reference ->
            DetailRow(stringResource(R.string.verify_trxid, card.channel)) {
                Text(
                    reference,
                    fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.Medium,
                    fontSize = 16.sp,
                    letterSpacing = 1.sp,
                )
            }
        }
        card.submitterPhone?.let { phone ->
            DetailRow(stringResource(R.string.verify_from)) {
                val shown = Numerals.phone(phone)
                Text(
                    when (card.submitterKey) {
                        "verify.from.guardian" -> stringResource(R.string.verify_from_guardian, shown)
                        "verify.from.student" -> stringResource(R.string.verify_from_student, shown)
                        else -> shown
                    },
                    style = BodyCompact,
                )
            }
        }
    }
}

/**
 * One label-and-value row.
 *
 * @param label The label, in a fixed-width column
 * @param value The value
 */
@Composable
private fun DetailRow(label: String, value: @Composable () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(width = 96.dp, height = 20.dp),
        )
        value()
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
 */
@Composable
private fun RecentList(rows: List<RecentRow>) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.verify_decided_today), style = MaterialTheme.typography.titleSmall)
        ShikkhokCard {
            rows.forEach { row ->
                Row(
                    Modifier.fillMaxWidth(),
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
                        when (row.statusKey) {
                            "verify.decision.approved_full" -> PaymentState.PAID
                            "verify.decision.approved_partial" -> PaymentState.PARTIAL
                            else -> PaymentState.DUE
                        },
                        stringResource(decisionLabel(row.statusKey)),
                        compact = true,
                    )
                }
            }
        }
    }
}

/**
 * The label for a claim decision.
 *
 * @param key The decision's key from the mapper
 * @return Its string resource
 */
private fun decisionLabel(key: String): Int =
    when (key) {
        "verify.decision.approved_full" -> R.string.verify_decision_paid
        "verify.decision.approved_partial" -> R.string.verify_decision_partial
        "verify.decision.rejected" -> R.string.verify_decision_rejected
        else -> R.string.verify_decision_pending
    }
