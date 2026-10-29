package com.shikkhokplus.app.feature.batchdetail.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.model.LinkState
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.batchdetail.FeeChip
import com.shikkhokplus.app.feature.batchdetail.FeeChipKind
import com.shikkhokplus.app.feature.batchdetail.FeeChips
import com.shikkhokplus.app.feature.roster.RosterRow
import com.shikkhokplus.app.feature.roster.RosterUiState
import com.shikkhokplus.app.feature.roster.ui.RemoveSeatConfirm
import com.shikkhokplus.app.feature.roster.ui.RemoveSeatRefused

/** One student row. */
const val TAG_STUDENT_ROW: String = "batch_student_row"

/** A student's fee chip. */
const val TAG_STUDENT_FEE: String = "batch_student_fee"

/** The fee-status failure card. */
const val TAG_FEES_FAILED: String = "batch_fees_failed"

/** The notice that the roster shown is a saved copy. */
const val TAG_STUDENTS_SAVED: String = "batch_students_saved"

/** The per-student actions under a tapped row. */
const val TAG_STUDENT_ACTIONS: String = "batch_student_actions"

/**
 * The Students tab: who is in the batch, and where each stands on fees.
 *
 * @param roster The roster's state
 * @param fees The fee chips
 * @param onAddFirst Called to add the first student
 * @param onFeeHistory Called with a row to open its fee history
 * @param onMarkInactive Called with a row to mark it inactive from today
 * @param onAskRemove Called with a row to ask to remove it
 * @param onRemove Called with a row the teacher confirmed removing
 * @param onCancelRemoval Called to back out of a removal
 * @param onRetry Called to read the roster again
 * @param onRetryFees Called to read the fees again
 */
@Composable
fun StudentsTab(
    roster: RosterUiState,
    fees: FeeChips,
    onAddFirst: () -> Unit,
    onFeeHistory: (RosterRow) -> Unit,
    onMarkInactive: (RosterRow) -> Unit,
    onAskRemove: (RosterRow) -> Unit,
    onRemove: (RosterRow) -> Unit,
    onCancelRemoval: () -> Unit,
    onRetry: () -> Unit,
    onRetryFees: () -> Unit,
) {
    when (roster) {
        RosterUiState.Idle, RosterUiState.Loading -> SkeletonList(rows = 5)
        is RosterUiState.Empty ->
            EmptyState(
                title = stringResource(R.string.batch_students_empty),
                body = stringResource(R.string.batch_students_empty_body),
                action = {
                    PrimaryButton(stringResource(R.string.batch_add_first_student), onAddFirst, Modifier.fillMaxWidth())
                },
            )
        is RosterUiState.Loaded -> StudentList(roster, fees, onFeeHistory, onMarkInactive, onAskRemove, onRetryFees)
        is RosterUiState.ConfirmingRemoval -> RemoveSeatConfirm(roster.row, onRemove, onCancelRemoval)
        is RosterUiState.RemovalRefused ->
            RemoveSeatRefused(roster.row, roster.remedy, onMarkInactive, onCancelRemoval)
        is RosterUiState.Failed ->
            ErrorCard(
                title = stringResource(R.string.batch_students_failed),
                body = stringResource(MessageKeys.resolve(roster.messageKey)),
                retryLabel = stringResource(R.string.roster_retry).takeIf { roster.retryable },
                onRetry = onRetry.takeIf { roster.retryable },
            )
    }
}

/**
 * The loaded roster: who has answered, then one row per student.
 *
 * @param roster The loaded roster
 * @param fees The fee chips
 * @param onFeeHistory Called with a row to open its fee history
 * @param onMarkInactive Called with a row to mark it inactive
 * @param onAskRemove Called with a row to ask to remove it
 * @param onRetryFees Called to read the fees again
 */
@Composable
private fun StudentList(
    roster: RosterUiState.Loaded,
    fees: FeeChips,
    onFeeHistory: (RosterRow) -> Unit,
    onMarkInactive: (RosterRow) -> Unit,
    onAskRemove: (RosterRow) -> Unit,
    onRetryFees: () -> Unit,
) {
    var open by remember { mutableStateOf<String?>(null) }
    LazyColumn(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium),
    ) {
        roster.accepted?.takeIf { it.accepted < it.total }?.let { count ->
            item {
                Banner(
                    title =
                        stringResource(
                            R.string.batch_accepted_count,
                            Numerals.count(count.accepted),
                            Numerals.count(count.total),
                        ),
                    body = stringResource(R.string.batch_accepted_body),
                    modifier = Modifier.padding(12.dp),
                )
            }
        }
        roster.fetchedAtLabel?.let { label ->
            item {
                // A READ cache, and it says so: a teacher must know when
                // they are looking at saved data rather than live data.
                Banner(
                    title = stringResource(R.string.roster_fetched_at, label),
                    tone = BannerTone.NEUTRAL,
                    modifier = Modifier.padding(12.dp).testTag(TAG_STUDENTS_SAVED),
                )
            }
        }
        if (fees == FeeChips.Failed) {
            item {
                ErrorCard(
                    title = stringResource(R.string.batch_fees_failed),
                    body = stringResource(R.string.batch_fees_failed_body),
                    retryLabel = stringResource(R.string.roster_retry),
                    onRetry = onRetryFees,
                    modifier = Modifier.padding(12.dp).testTag(TAG_FEES_FAILED),
                )
            }
        }
        items(roster.rows, key = { it.enrollmentId }) { row ->
            StudentRow(
                row = row,
                chip = (fees as? FeeChips.Loaded)?.bySeat?.get(row.enrollmentId),
                expanded = open == row.enrollmentId,
                onToggle = { open = if (open == row.enrollmentId) null else row.enrollmentId },
                onFeeHistory = onFeeHistory,
                onMarkInactive = onMarkInactive,
                onAskRemove = onAskRemove,
            )
            HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
        }
        item { Column(Modifier.heightIn(min = 88.dp)) {} }
    }
}

/**
 * One student: name, guardian line, fee chip; tapped, its actions.
 *
 * @param row The student
 * @param chip Their fee chip, if any
 * @param expanded Whether the actions are showing
 * @param onToggle Called when the row is tapped
 * @param onFeeHistory Called to open fee history
 * @param onMarkInactive Called to mark inactive from today
 * @param onAskRemove Called to ask to remove
 */
@Composable
private fun StudentRow(
    row: RosterRow,
    chip: FeeChip?,
    expanded: Boolean,
    onToggle: () -> Unit,
    onFeeHistory: (RosterRow) -> Unit,
    onMarkInactive: (RosterRow) -> Unit,
    onAskRemove: (RosterRow) -> Unit,
) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onToggle).testTag(TAG_STUDENT_ROW)) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 64.dp).padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                // **`displayLabel`, never `displayName`** [BR2.3,
                // NFR14.28]: a declined seat shows the number, because
                // a name names a person who said the seat is not theirs
                // and a mistyped number is what the teacher must fix.
                // No number recorded shows a placeholder, not the name.
                Text(
                    row.displayLabel?.let { if (row.isDeclined) Numerals.phone(it) else Numerals.freeText(it) }
                        ?: stringResource(R.string.roster_declined_no_number),
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    subline(row),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            when {
                row.isDeclined ->
                    PaymentStateChip(PaymentState.DUE, stringResource(R.string.batch_declined), compact = true)
                chip != null -> FeeChipView(chip)
            }
        }
        if (row.isDeclined) {
            Text(
                stringResource(R.string.batch_declined_help),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
        if (expanded || row.isDeclined) {
            Row(Modifier.padding(horizontal = 8.dp).testTag(TAG_STUDENT_ACTIONS)) {
                if (!row.isDeclined) {
                    TextAction(stringResource(R.string.batch_fee_history), { onFeeHistory(row) })
                    TextAction(stringResource(R.string.batch_mark_inactive), { onMarkInactive(row) })
                }
                if (row.isRemovable) {
                    TextAction(stringResource(R.string.batch_remove), { onAskRemove(row) })
                }
            }
        }
    }
}

/**
 * The line under a name: a custom fee, then the guardian, then who has
 * not answered.
 *
 * @param row The student
 * @return The line
 */
@Composable
private fun subline(row: RosterRow): String {
    if (row.isDeclined) return stringResource(R.string.batch_declined_by_number)
    val parts = mutableListOf<String>()
    row.fee?.let { parts += stringResource(R.string.batch_custom_fee, Numerals.money(it)) }
    val phone = row.guardianPhone
    parts +=
        when {
            phone == null -> stringResource(R.string.batch_no_guardian)
            row.guardianState == LinkState.DECLINED -> stringResource(R.string.batch_guardian_declined)
            else -> stringResource(R.string.batch_guardian, Numerals.phone(phone))
        }
    if (row.studentState == LinkState.PENDING) parts += stringResource(R.string.batch_not_answered)
    return parts.joinToString(" · ")
}

/**
 * A fee chip, in the words the board uses for each kind.
 *
 * @param chip The chip
 */
@Composable
private fun FeeChipView(chip: FeeChip) {
    val amount = chip.amount?.let(Numerals::money).orEmpty()
    val (state, label) =
        when (chip.kind) {
            FeeChipKind.VERIFYING -> PaymentState.VERIFYING to stringResource(R.string.batch_fee_verifying, amount)
            FeeChipKind.OVERDUE ->
                PaymentState.OVERDUE to
                    stringResource(R.string.batch_fee_overdue, amount, Numerals.count(chip.days ?: 0))
            FeeChipKind.PARTIAL -> PaymentState.PARTIAL to stringResource(R.string.batch_fee_left, amount)
            FeeChipKind.PAID -> PaymentState.PAID to stringResource(R.string.fees_status_paid)
            FeeChipKind.WAIVED -> PaymentState.PAID to stringResource(R.string.fees_status_waived)
            FeeChipKind.DUE ->
                PaymentState.DUE to stringResource(R.string.batch_fee_due_on, dueLabel(chip.dueDate))
        }
    PaymentStateChip(state, label, compact = true, modifier = Modifier.testTag(TAG_STUDENT_FEE))
}

/**
 * A due date as the chip says it: `20 Oct`.
 *
 * @param iso `YYYY-MM-DD`, or null
 * @return The short date
 */
private fun dueLabel(iso: String?): String {
    val date = iso ?: return ""
    val day = date.takeLast(2).trimStart('0')
    return "$day ${monthName(date.take(PERIOD_LENGTH))}"
}

/** `YYYY-MM` out of a date. */
private const val PERIOD_LENGTH = 7
