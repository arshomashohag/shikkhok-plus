package com.shikkhokplus.app.feature.verify.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.DestructiveButton
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.MoneyLead
import com.shikkhokplus.app.core.designsystem.Motion
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.rememberHaptics
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dateTimeLabel
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.verify.ApprovalSheet
import com.shikkhokplus.app.feature.verify.DuplicateNote
import com.shikkhokplus.app.feature.verify.MethodKind
import com.shikkhokplus.app.feature.verify.REVIEW_NOTE_MAX
import com.shikkhokplus.app.feature.verify.ReviewCard
import com.shikkhokplus.app.feature.verify.ReviewMethod
import com.shikkhokplus.app.feature.verify.ReviewStatus
import com.shikkhokplus.app.feature.verify.ReviewUiState

/** The note to the family. */
const val TAG_REVIEW_NOTE: String = "review_note"

/** Approve, from the payment itself. */
const val TAG_VERIFY_APPROVE: String = "verify_approve"

/** Reject, from the payment itself. */
const val TAG_VERIFY_REJECT: String = "verify_reject"

/** The reject confirmation's confirm button. */
const val TAG_VERIFY_REJECT_CONFIRM: String = "verify_reject_confirm"

/** The duplicate-reference warning. */
const val TAG_VERIFY_DUPLICATE: String = "verify_duplicate"

/** Opens the sheet to approve a different amount. */
const val TAG_REVIEW_APPROVE_OTHER: String = "review_approve_other"

/** Re-opens a decided payment for a new decision. */
const val TAG_REVIEW_CHANGE: String = "review_change_decision"

/** The teacher's note on a decided payment. */
const val TAG_REVIEW_DECISION_NOTE: String = "review_decision_note"

/** One child on the payment; the child's seat id follows an underscore. */
const val TAG_REVIEW_CHILD: String = "review_child"

/** What the children owe together. */
const val TAG_REVIEW_OWED_TOGETHER: String = "review_owed_together"

/** A refused or failed decision, shown above the payment. */
const val TAG_VERIFY_ERROR: String = "verify_error"

/**
 * What the payment screen can do, grouped so the screen stays readable.
 *
 * @property onBack Leave the screen
 * @property onApprove Approve, with the note typed so far
 * @property onApproveOther Open the sheet, with the note typed so far
 * @property onReject Reject, with the note typed so far
 * @property onChangeDecision Offer a decided payment's actions again
 * @property onRetry Read the payment again
 * @property sheet What the approval sheet can do
 */
class ReviewActions(
    val onBack: () -> Unit,
    val onApprove: (String) -> Unit,
    val onApproveOther: (String) -> Unit,
    val onReject: (String) -> Unit,
    val onChangeDecision: () -> Unit,
    val onRetry: () -> Unit,
    val sheet: SheetActions,
)

/**
 * R2 and R3: one payment, to check or already decided.
 *
 * Every figure and the comparison are the server's; nothing here
 * subtracts or splits money [TC-9].
 *
 * @param state What to render
 * @param sheet The approval sheet, while open
 * @param actions What the screen can do
 * @param modifier The layout modifier
 */
@Composable
fun PaymentReviewScreen(
    state: ReviewUiState,
    sheet: ApprovalSheet?,
    actions: ReviewActions,
    modifier: Modifier = Modifier,
) {
    val decided = (state as? ReviewUiState.Loaded)?.card?.status?.let { it != ReviewStatus.PENDING } == true
    DecisionHaptics(state as? ReviewUiState.Loaded)
    ListScreenScaffold(
        title = stringResource(if (decided) R.string.verify_detail_title_decided else R.string.verify_detail_title),
        onBack = actions.onBack,
        modifier = modifier,
    ) {
        when (state) {
            ReviewUiState.Loading -> SkeletonList(rows = 3)
            is ReviewUiState.Failed ->
                ErrorCard(
                    title = stringResource(R.string.verify_detail_load_failed),
                    body = stringResource(MessageKeys.resolve(state.messageKey)),
                    retryLabel = stringResource(R.string.roster_retry).takeIf { state.retryable },
                    onRetry = actions.onRetry.takeIf { state.retryable },
                )
            is ReviewUiState.Loaded -> Loaded(state, actions)
        }
    }
    if (state is ReviewUiState.Loaded) {
        sheet?.let { ApprovalSheetView(it, state.busy, state.errorKey, actions.sheet) }
    }
}

/**
 * The loaded payment: who sent what, then the decision or its record.
 *
 * @param state The loaded payment
 * @param actions What the screen can do
 */
@Composable
private fun Loaded(state: ReviewUiState.Loaded, actions: ReviewActions) {
    val card = state.card
    var note by rememberSaveable { mutableStateOf("") }
    var rejecting by rememberSaveable { mutableStateOf(false) }
    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        state.errorKey?.let { key ->
            Banner(
                title = stringResource(MessageKeys.resolve(key)),
                tone = BannerTone.ERROR,
                modifier = Modifier.testTag(TAG_VERIFY_ERROR),
            )
        }
        Summary(card)
        Facts(card)
        card.duplicate?.let { Duplicate(it) }
            ?: Text(
                stringResource(R.string.verify_no_duplicate),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        // The controls give way to the decision when it lands, and back
        // when the teacher chooses to change it: a fade rather than a
        // jump, so the eye follows the card that replaced the buttons.
        AnimatedContent(
            targetState = state.canDecide,
            transitionSpec = { fadeIn(tween(Motion.ENTER_MS)) togetherWith fadeOut(tween(Motion.EXIT_MS)) },
            label = "decision",
        ) { deciding ->
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (deciding) {
                    DecideControls(state, note, { note = it }, { rejecting = true }, actions)
                } else {
                    Decision(card)
                    TextAction(
                        stringResource(R.string.verify_change_decision),
                        actions.onChangeDecision,
                        Modifier.fillMaxWidth().testTag(TAG_REVIEW_CHANGE),
                    )
                }
            }
        }
    }
    if (rejecting) {
        AlertDialog(
            onDismissRequest = { rejecting = false },
            title = { Text(stringResource(R.string.verify_reject_title)) },
            text = {
                Text(
                    stringResource(
                        R.string.verify_reject_body,
                        Numerals.freeText(card.displayName),
                        Numerals.money(card.totalAmount),
                    ),
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        rejecting = false
                        actions.onReject(note)
                    },
                    modifier = Modifier.testTag(TAG_VERIFY_REJECT_CONFIRM),
                ) { Text(stringResource(R.string.verify_reject), color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { rejecting = false }) { Text(stringResource(R.string.action_cancel)) }
            },
        )
    }
}

/**
 * Approve, reject or approve a different amount, with a note to the
 * family.
 *
 * @param state The loaded payment
 * @param note The note typed so far
 * @param onNote Called with the edited note
 * @param onAskReject Opens the reject confirmation
 * @param actions What the screen can do
 */
@Composable
private fun DecideControls(
    state: ReviewUiState.Loaded,
    note: String,
    onNote: (String) -> Unit,
    onAskReject: () -> Unit,
    actions: ReviewActions,
) {
    ShikkhokTextField(
        value = note,
        onValueChange = { onNote(it.take(REVIEW_NOTE_MAX)) },
        label = stringResource(R.string.verify_note_to_them),
        singleLine = false,
        minLines = 2,
        fieldModifier = Modifier.testTag(TAG_REVIEW_NOTE),
    )
    TextAction(
        stringResource(R.string.verify_approve_other),
        { actions.onApproveOther(note) },
        Modifier.fillMaxWidth().testTag(TAG_REVIEW_APPROVE_OTHER),
        enabled = !state.busy,
    )
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        DestructiveButton(
            text = stringResource(R.string.verify_reject),
            onClick = onAskReject,
            enabled = !state.busy,
            modifier = Modifier.testTag(TAG_VERIFY_REJECT),
        )
        PrimaryButton(
            text = stringResource(R.string.verify_approve),
            onClick = { actions.onApprove(note) },
            enabled = !state.busy,
            modifier = Modifier.weight(1f).testTag(TAG_VERIFY_APPROVE),
        )
    }
}

/**
 * Buzz once when a decision the teacher made has landed.
 *
 * **On the write's answer, not on the tap.** The tap already has its
 * ripple; what a teacher holding a bKash statement in the other hand
 * cannot otherwise feel is that the server accepted it. So this fires
 * when a write that was in flight (`busy`) ends with no error, and
 * never when an already-decided payment is merely opened.
 *
 * @param state The loaded payment, or null while loading or failed
 */
@Composable
private fun DecisionHaptics(state: ReviewUiState.Loaded?) {
    val haptics = rememberHaptics()
    var wasBusy by remember { mutableStateOf(false) }
    LaunchedEffect(state?.busy, state?.errorKey, state?.card?.status) {
        val busy = state?.busy == true
        if (wasBusy && !busy && state != null && state.errorKey == null) {
            when (state.card.status) {
                ReviewStatus.APPROVED -> haptics.confirm()
                ReviewStatus.REJECTED -> haptics.reject()
                ReviewStatus.PENDING -> Unit
            }
        }
        wasBusy = busy
    }
}

/**
 * Who it is for, how much, and how it compares.
 *
 * @param card The payment
 */
@Composable
private fun Summary(card: ReviewCard) {
    ShikkhokCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(Numerals.freeText(card.displayName), style = MaterialTheme.typography.titleMedium)
                Text(
                    Numerals.freeText(card.batchName),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            // The chip changes with the decision; a crossfade marks the
            // change so it is seen rather than discovered.
            Crossfade(targetState = card.status, animationSpec = tween(Motion.ENTER_MS), label = "status") { status ->
                StatusChip(status)
            }
        }
        Text(Numerals.money(card.totalAmount), style = MoneyLead)
        ComparisonChip(card)
        card.children.forEach { child ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .semantics(mergeDescendants = true) {}
                    .testTag("${TAG_REVIEW_CHILD}_${child.enrollmentId}"),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    stringResource(
                        R.string.verify_child_line,
                        Numerals.freeText(child.displayName),
                        monthName(child.period, short = false),
                    ),
                    style = BodyCompact,
                )
                Text(Numerals.money(child.owed), style = BodyCompact)
            }
        }
        Row(
            Modifier.fillMaxWidth().semantics(mergeDescendants = true) {}.testTag(TAG_REVIEW_OWED_TOGETHER),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(stringResource(R.string.verify_owed_together), style = MaterialTheme.typography.titleSmall)
            Text(Numerals.money(card.owedTogether), style = MaterialTheme.typography.titleSmall)
        }
    }
}

/**
 * The status as a chip, in the family-facing words.
 *
 * @param status Where the review stands
 */
@Composable
private fun StatusChip(status: ReviewStatus) {
    val (state, label) =
        when (status) {
            ReviewStatus.PENDING -> PaymentState.PARTIAL to R.string.verify_decision_pending
            ReviewStatus.APPROVED -> PaymentState.PAID to R.string.verify_decision_approved
            ReviewStatus.REJECTED -> PaymentState.DUE to R.string.verify_decision_rejected
        }
    PaymentStateChip(state, stringResource(label), compact = true)
}

/**
 * The facts to check against a statement: sender, method, reference, dates.
 *
 * @param card The payment
 */
@Composable
private fun Facts(card: ReviewCard) {
    ShikkhokCard {
        card.submitterPhone?.let { phone ->
            val shown = Numerals.phone(phone)
            Fact(stringResource(R.string.verify_sent_by)) {
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
        Fact(stringResource(R.string.verify_method)) { Text(methodLine(card.method), style = BodyCompact) }
        card.transactionId?.let { reference ->
            Fact(stringResource(R.string.verify_transaction_id)) {
                Text(
                    reference,
                    fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.Medium,
                    letterSpacing = 1.sp,
                )
            }
        }
        card.fromAccount?.let { account ->
            Fact(stringResource(R.string.verify_paid_from)) { Text(Numerals.freeText(account), style = BodyCompact) }
        }
        Fact(stringResource(R.string.verify_paid_on)) { Text(shortDate(card.paidOn), style = BodyCompact) }
        Fact(stringResource(R.string.verify_submitted)) {
            Text("${dateTimeLabel(card.submittedAt)} · ${ago(card.submittedAt)}", style = BodyCompact)
        }
        card.payerNote?.let { payerNote ->
            Fact(stringResource(R.string.verify_their_note)) {
                Text(Numerals.freeText(payerNote), style = BodyCompact)
            }
        }
    }
}

/**
 * One label-and-value row.
 *
 * @param label The label
 * @param value The value
 */
@Composable
private fun Fact(label: String, value: @Composable () -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.size(width = 104.dp, height = 20.dp),
        )
        Column(Modifier.weight(1f)) { value() }
    }
}

/**
 * Where the money was sent, in a line.
 *
 * @param method The destination snapshot
 * @return The line
 */
@Composable
private fun methodLine(method: ReviewMethod): String {
    val provider = Numerals.freeText(method.provider.orEmpty())
    val number = method.number.orEmpty()
    return when (method.kind) {
        MethodKind.MOBILE -> stringResource(R.string.verify_method_mobile, provider, Numerals.phone(number))
        MethodKind.BANK -> stringResource(R.string.verify_method_bank, provider, number)
        MethodKind.CASH -> stringResource(R.string.verify_method_cash)
        MethodKind.OTHER -> provider
    }
}

/**
 * The warning that a reference was used before.
 *
 * @param duplicate The earlier payment
 */
@Composable
private fun Duplicate(duplicate: DuplicateNote) {
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

/**
 * A decided payment's record: who decided when, and the note they left.
 *
 * @param card The decided payment
 */
@Composable
private fun Decision(card: ReviewCard) {
    val rejected = card.status == ReviewStatus.REJECTED
    ShikkhokCard {
        card.decidedAt?.let { at ->
            Text(
                stringResource(
                    if (rejected) R.string.verify_decided_by_you_rejected else R.string.verify_decided_by_you_approved,
                    dateTimeLabel(at),
                ),
                style = MaterialTheme.typography.titleSmall,
            )
        }
        card.decisionNote?.let { note ->
            Text(
                "“${Numerals.freeText(note)}”",
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier.testTag(TAG_REVIEW_DECISION_NOTE),
            )
        }
        if (rejected) {
            Text(
                stringResource(R.string.verify_rejected_help),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
