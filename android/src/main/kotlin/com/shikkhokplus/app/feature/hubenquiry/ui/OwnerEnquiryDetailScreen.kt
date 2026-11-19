package com.shikkhokplus.app.feature.hubenquiry.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dateTimeLabel
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hubenquiry.EnquiryOutcome
import com.shikkhokplus.app.feature.hubenquiry.OwnerEnquiry
import com.shikkhokplus.app.feature.hubenquiry.OwnerEnquiryUiState
import com.shikkhokplus.app.feature.hubenquiry.OwnerEnquiryView
import com.shikkhokplus.app.feature.hubreviews.ui.Notice
import com.shikkhokplus.app.feature.hubreviews.ui.Quiet

/** The guardian's shared phone, as a call action. */
const val TAG_ENQUIRY_CONTACT_PHONE: String = "hub_enquiry_contact_phone"

/** The guardian's shared email, as a write action. */
const val TAG_ENQUIRY_CONTACT_EMAIL: String = "hub_enquiry_contact_email"

/** Retry after a failed answer. */
const val TAG_ENQUIRY_CLOSE_RETRY: String = "hub_enquiry_close_retry"

/**
 * Tag for one answer's button.
 *
 * @param outcome The answer
 * @return The tag
 */
fun enquiryActionTag(outcome: EnquiryOutcome): String = "hub_enquiry_action_${outcome.wire}"

/**
 * What one owner request can do.
 *
 * @property onAdd Opens the add-student form filled from the request
 * @property onAnswer Sends an answer other than adding
 * @property onRetry Sends the failed answer again
 * @property onRetryLoad Reads again
 * @property onCall Dials the guardian's shared phone
 * @property onEmail Writes to the guardian's shared email
 * @property onDismissNotice Forgets the "answer sent" confirmation
 * @property onBack Leaves the screen
 */
data class OwnerEnquiryActions(
    val onAdd: (OwnerEnquiry) -> Unit = {},
    val onAnswer: (EnquiryOutcome) -> Unit = {},
    val onRetry: () -> Unit = {},
    val onRetryLoad: () -> Unit = {},
    val onCall: (String) -> Unit = {},
    val onEmail: (String) -> Unit = {},
    val onDismissNotice: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * One join request, as the owner reads it [H5]: status, student, class,
 * message, batch, when it arrived, and the guardian's contact as a call or
 * an email only when the server sent one, which it does only while the
 * guardian chose to share it; otherwise "Not shared".
 *
 * **The answers offered are exactly `outcomes_allowed`.** "Add as student"
 * opens the add-student form filled from the request, which answers once
 * the student is saved; the others are sent from here. A refused answer
 * reads in the server's words. Switched off, or for a request that is
 * gone, the screen says so plainly, with no Retry.
 *
 * @param state What to render
 * @param actions What the controls do
 * @param modifier Layout modifier from the caller
 */
@Composable
fun OwnerEnquiryDetailScreen(
    state: OwnerEnquiryUiState,
    actions: OwnerEnquiryActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.hub_enquiry_detail_title),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        when (state) {
            OwnerEnquiryUiState.Loading -> SkeletonList(rows = 4)
            is OwnerEnquiryUiState.Unavailable ->
                Banner(title = stringResource(MessageKeys.resolve(state.messageKey)), tone = BannerTone.INFO)
            is OwnerEnquiryUiState.Error ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = stringResource(R.string.auth_retry),
                    onRetry = actions.onRetryLoad,
                )
            is OwnerEnquiryUiState.Ready -> Detail(state.view, actions)
        }
    }
}

/**
 * The request's fields, the last answer's failure, and the answers offered.
 *
 * @param view The request and the answer in hand
 * @param actions What the controls do
 */
@Composable
private fun Detail(view: OwnerEnquiryView, actions: OwnerEnquiryActions) {
    val enquiry = view.enquiry
    if (view.answered) Notice(stringResource(R.string.hub_enquiry_closed_snack), actions.onDismissNotice)
    ShikkhokCard {
        OwnerStatus(enquiry)
        Field(stringResource(R.string.hub_enquiry_student_name), Numerals.freeText(enquiry.studentName))
        Field(stringResource(R.string.hub_enquiry_class_level), levelText(enquiry.classLevel))
        enquiry.message?.let { Field(stringResource(R.string.hub_enquiry_field_message), Numerals.freeText(it)) }
        Field(
            stringResource(R.string.hub_enquiry_field_batch),
            enquiry.batchTitle?.let(Numerals::freeText) ?: stringResource(R.string.hub_enquiry_any_class),
        )
        Field(stringResource(R.string.hub_enquiry_field_received), dateTimeLabel(enquiry.receivedAt))
        Quiet(stringResource(R.string.hub_enquiry_field_contact))
        Contact(enquiry, actions)
    }
    view.failure?.let { failure ->
        Banner(
            title = stringResource(R.string.hub_enquiry_close_failed),
            body = stringResource(MessageKeys.resolve(failure.messageKey)),
            tone = BannerTone.ERROR,
            action =
                if (view.retryOutcome != null) {
                    {
                        TextAction(
                            stringResource(R.string.auth_retry),
                            actions.onRetry,
                            Modifier.testTag(TAG_ENQUIRY_CLOSE_RETRY),
                        )
                    }
                } else {
                    null
                },
        )
    }
    enquiry.offered.forEach { outcome ->
        val modifier = Modifier.fillMaxWidth().testTag(enquiryActionTag(outcome))
        val label = stringResource(actionText(outcome))
        if (outcome == EnquiryOutcome.ADDED) {
            // Adding is the add-student form's to finish: it saves, then answers.
            PrimaryButton(label, { actions.onAdd(enquiry) }, modifier, enabled = !view.closing)
        } else {
            SecondaryButton(label, { actions.onAnswer(outcome) }, modifier, enabled = !view.closing)
        }
    }
}

/**
 * The guardian's contact: a call, an email, or "Not shared".
 *
 * @param enquiry The request
 * @param actions What a tap does
 */
@Composable
private fun Contact(enquiry: OwnerEnquiry, actions: OwnerEnquiryActions) {
    val phone = enquiry.guardianPhone
    val email = enquiry.guardianEmail
    when {
        phone != null ->
            TextAction(Numerals.phone(phone), { actions.onCall(phone) }, Modifier.testTag(TAG_ENQUIRY_CONTACT_PHONE))
        email != null -> TextAction(email, { actions.onEmail(email) }, Modifier.testTag(TAG_ENQUIRY_CONTACT_EMAIL))
        else ->
            Text(stringResource(R.string.hub_enquiry_contact_not_shared), style = MaterialTheme.typography.bodyLarge)
    }
}

/** A label above its value. */
@Composable
private fun Field(label: String, value: String) {
    Quiet(label)
    Text(value, style = MaterialTheme.typography.bodyLarge)
}

/**
 * An answer's button label.
 *
 * @param outcome The answer
 * @return Its string resource
 */
private fun actionText(outcome: EnquiryOutcome): Int =
    when (outcome) {
        EnquiryOutcome.ADDED -> R.string.hub_enquiry_action_add
        EnquiryOutcome.NOT_NOW -> R.string.hub_enquiry_action_not_now
        EnquiryOutcome.CALL_US -> R.string.hub_enquiry_action_call_us
    }
