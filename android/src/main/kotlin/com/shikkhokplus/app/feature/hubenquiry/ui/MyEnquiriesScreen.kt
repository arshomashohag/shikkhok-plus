package com.shikkhokplus.app.feature.hubenquiry.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.DeleteDialog
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.Notice
import com.shikkhokplus.app.core.designsystem.Quiet
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayMonthYear
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hubenquiry.EnquiryFailure
import com.shikkhokplus.app.feature.hubenquiry.EnquiryOutcome
import com.shikkhokplus.app.feature.hubenquiry.MyEnquiriesUiState
import com.shikkhokplus.app.feature.hubenquiry.MyEnquiry
import com.shikkhokplus.app.feature.hubenquiry.STATUS_OPEN
import com.shikkhokplus.app.feature.hubenquiry.WithdrawFailure

/** The withdrawal confirmation's Withdraw button. */
const val TAG_ENQUIRY_WITHDRAW_CONFIRM: String = "hub_enquiry_withdraw_confirm"

/** The banner saying the list shown could not be read again. */
const val TAG_ENQUIRY_REFRESH_FAILED: String = "hub_enquiry_refresh_failed"

/** Retry after a failed withdrawal. */
const val TAG_ENQUIRY_WITHDRAW_RETRY: String = "hub_enquiry_withdraw_retry"

/**
 * Tag for one request's row.
 *
 * @param enquiryId The request
 * @return The tag
 */
fun myEnquiryRowTag(enquiryId: String): String = "hub_my_enquiry_$enquiryId"

/**
 * Tag for one request's Withdraw.
 *
 * @param enquiryId The request
 * @return The tag
 */
fun myEnquiryWithdrawTag(enquiryId: String): String = "hub_my_enquiry_withdraw_$enquiryId"

/**
 * What the guardian's join-request list can do.
 *
 * @property onWithdraw Opens the confirmation for a request
 * @property onConfirmWithdraw Withdraws
 * @property onCancelWithdraw Closes the confirmation
 * @property onRetryWithdraw Asks again after a failed withdrawal
 * @property onCall Dials the owner's published number
 * @property onRetry Reads again
 * @property onDismissNotice Forgets the "withdrawn" confirmation
 * @property onBack Leaves the screen
 */
data class MyEnquiriesActions(
    val onWithdraw: (String) -> Unit = {},
    val onConfirmWithdraw: () -> Unit = {},
    val onCancelWithdraw: () -> Unit = {},
    val onRetryWithdraw: () -> Unit = {},
    val onCall: (String) -> Unit = {},
    val onRetry: () -> Unit = {},
    val onDismissNotice: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The caller's own join requests [H5], whatever their lens: who each went
 * to, for whom, and where it stands, each with Withdraw.
 *
 * **The server's codes, in words.** An open request is waiting; a closed
 * one reads the owner's answer from its outcome code, and a `call_us`
 * answer offers the owner's published number when the server sent one. A
 * request whose listing has gone reads as a teacher no longer listed.
 * Withdrawal deletes completely and is sent only from the confirmation
 * that says so.
 *
 * @param state What to render
 * @param actions What the controls do
 * @param modifier Layout modifier from the caller
 */
@Composable
fun MyEnquiriesScreen(
    state: MyEnquiriesUiState,
    actions: MyEnquiriesActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.hub_enquiry_mine_title),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        when (state) {
            MyEnquiriesUiState.Loading -> SkeletonList(rows = 3)
            is MyEnquiriesUiState.Error ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            is MyEnquiriesUiState.Ready -> {
                if (state.withdrawn) Notice(stringResource(R.string.hub_enquiry_withdrawn), actions.onDismissNotice)
                state.refreshFailure?.let { RefreshFailed(it, actions.onRetry) }
                if (state.rows.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.hub_enquiry_mine_empty),
                        body = stringResource(R.string.hub_enquiry_mine_sub),
                    )
                }
                state.rows.forEach { row ->
                    RequestRow(
                        row = row,
                        busy = state.withdrawing,
                        failure = state.failure?.takeIf { it.enquiryId == row.id },
                        actions = actions,
                    )
                }
            }
        }
    }
    if ((state as? MyEnquiriesUiState.Ready)?.confirming != null) {
        DeleteDialog(
            title = stringResource(R.string.hub_enquiry_withdraw_title),
            body = stringResource(R.string.hub_enquiry_withdraw_body),
            confirm = stringResource(R.string.hub_enquiry_withdraw),
            confirmTag = TAG_ENQUIRY_WITHDRAW_CONFIRM,
            onConfirm = actions.onConfirmWithdraw,
            onCancel = actions.onCancelWithdraw,
        )
    }
}

/**
 * One request: who it went to, for whom, where it stands, and Withdraw.
 *
 * @param row The server's row
 * @param busy Whether a withdrawal is in flight
 * @param failure The failed withdrawal of this row, or null
 * @param actions What the controls do
 */
@Composable
private fun RequestRow(row: MyEnquiry, busy: Boolean, failure: WithdrawFailure?, actions: MyEnquiriesActions) {
    ShikkhokCard(modifier = Modifier.testTag(myEnquiryRowTag(row.id))) {
        Text(
            row.ownerPublicName?.let(Numerals::freeText) ?: stringResource(R.string.hub_enquiry_owner_unknown),
            style = MaterialTheme.typography.titleMedium,
        )
        row.batchTitle?.let { Quiet(Numerals.freeText(it)) }
        Quiet(
            listOf(
                Numerals.freeText(row.studentName),
                levelText(row.classLevel),
                stringResource(R.string.hub_enquiry_sent_on, dayMonthYear(row.sentOn)),
            ).filter { it.isNotEmpty() }.joinToString(" · "),
        )
        val outcome = EnquiryOutcome.fromWire(row.outcome)
        when {
            row.status == STATUS_OPEN ->
                Text(
                    stringResource(R.string.hub_enquiry_status_open),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
            outcome != null ->
                Text(stringResource(guardianOutcomeText(outcome)), style = MaterialTheme.typography.bodyLarge)
        }
        row.ownerContactPhone?.takeIf { outcome == EnquiryOutcome.CALL_US }?.let { phone ->
            TextAction(
                stringResource(R.string.hub_enquiry_call_owner, Numerals.phone(phone)),
                { actions.onCall(phone) },
            )
        }
        TextAction(
            stringResource(R.string.hub_enquiry_withdraw),
            { actions.onWithdraw(row.id) },
            Modifier.testTag(myEnquiryWithdrawTag(row.id)),
            enabled = !busy,
        )
        failure?.let { failed ->
            Banner(
                title = stringResource(R.string.hub_enquiry_withdraw_failed),
                body = stringResource(MessageKeys.resolve(failed.failure.messageKey)),
                tone = BannerTone.ERROR,
                action =
                    if (failed.failure.canRetry) {
                        {
                            TextAction(
                                stringResource(R.string.auth_retry),
                                actions.onRetryWithdraw,
                                Modifier.testTag(TAG_ENQUIRY_WITHDRAW_RETRY),
                            )
                        }
                    } else {
                        null
                    },
            )
        }
    }
}

/**
 * The guardian's line for the owner's answer.
 *
 * @param outcome The answer
 * @return Its string resource
 */
internal fun guardianOutcomeText(outcome: EnquiryOutcome): Int =
    when (outcome) {
        EnquiryOutcome.ADDED -> R.string.hub_enquiry_outcome_added
        EnquiryOutcome.NOT_NOW -> R.string.hub_enquiry_outcome_not_now
        EnquiryOutcome.CALL_US -> R.string.hub_enquiry_outcome_call_us
    }

/**
 * The rows shown are the last ones read: a quiet re-read failed. Said in
 * the server's words, or the offline line, with Retry when it can help.
 *
 * @param failure Why the re-read failed
 * @param onRetry Reads again
 */
@Composable
internal fun RefreshFailed(failure: EnquiryFailure, onRetry: () -> Unit) {
    Banner(
        title = stringResource(MessageKeys.resolve(failure.messageKey)),
        tone = BannerTone.NEUTRAL,
        modifier = Modifier.testTag(TAG_ENQUIRY_REFRESH_FAILED),
        action =
            if (failure.canRetry) {
                { TextAction(stringResource(R.string.auth_retry), onRetry) }
            } else {
                null
            },
    )
}
