package com.shikkhokplus.app.feature.hubenquiry.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.Quiet
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dateTimeLabel
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hubenquiry.EnquiryOutcome
import com.shikkhokplus.app.feature.hubenquiry.OwnerEnquiriesUiState
import com.shikkhokplus.app.feature.hubenquiry.OwnerEnquiry
import com.shikkhokplus.app.feature.hubenquiry.STATUS_OPEN
import com.shikkhokplus.app.feature.hubenquiry.classLevelOf
import com.shikkhokplus.app.feature.hublisting.ui.levelLabel

/**
 * Tag for one request's row in the owner's inbox.
 *
 * @param enquiryId The request
 * @return The tag
 */
fun ownerEnquiryRowTag(enquiryId: String): String = "hub_owner_enquiry_$enquiryId"

/**
 * What the owner's inbox can do.
 *
 * @property onOpen Opens a request
 * @property onRetry Reads again
 * @property onBack Leaves the screen
 */
data class OwnerEnquiriesActions(
    val onOpen: (OwnerEnquiry) -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The owner's join requests [H5], in the server's order, open first. A
 * row names the student, the class, the batch asked about and when; the
 * guardian's contact is never in the list. Opened while join requests are
 * switched off, the screen says so plainly, with no Retry.
 *
 * @param state What to render
 * @param actions What the rows do
 * @param modifier Layout modifier from the caller
 */
@Composable
fun OwnerEnquiriesScreen(
    state: OwnerEnquiriesUiState,
    actions: OwnerEnquiriesActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.hub_enquiry_inbox_title),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        when (state) {
            OwnerEnquiriesUiState.Loading -> SkeletonList(rows = 3)
            is OwnerEnquiriesUiState.Off ->
                Banner(title = stringResource(MessageKeys.resolve(state.messageKey)), tone = BannerTone.INFO)
            is OwnerEnquiriesUiState.Error ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            is OwnerEnquiriesUiState.Ready ->
                if (state.rows.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.hub_enquiry_inbox_empty),
                        body = stringResource(R.string.hub_enquiry_inbox_sub),
                    )
                } else {
                    state.rows.forEach { row -> InboxRow(row) { actions.onOpen(row) } }
                }
        }
    }
}

/**
 * One request: the student, the class, the batch or "Any class", when, and its status.
 *
 * @param row The server's row
 * @param onOpen Opens it
 */
@Composable
private fun InboxRow(row: OwnerEnquiry, onOpen: () -> Unit) {
    ShikkhokCard(modifier = Modifier.testTag(ownerEnquiryRowTag(row.id)), onClick = onOpen) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(Numerals.freeText(row.studentName), style = MaterialTheme.typography.titleMedium)
                Quiet(
                    listOf(
                        levelText(row.classLevel),
                        row.batchTitle?.let(Numerals::freeText) ?: stringResource(R.string.hub_enquiry_any_class),
                        dateTimeLabel(row.receivedAt),
                    ).filter { it.isNotEmpty() }.joinToString(" · "),
                )
            }
            Column(Modifier.padding(start = 12.dp), horizontalAlignment = Alignment.End) {
                OwnerStatus(row)
            }
        }
    }
}

/**
 * Open, or the answer given, in the owner's words.
 *
 * @param enquiry The request
 */
@Composable
internal fun OwnerStatus(enquiry: OwnerEnquiry) {
    val words =
        if (enquiry.status == STATUS_OPEN) {
            R.string.hub_enquiry_needs_answer
        } else {
            EnquiryOutcome.fromWire(enquiry.outcome)?.let(::ownerOutcomeText)
        }
    words?.let {
        Text(stringResource(it), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
    }
}

/**
 * The owner's line for their own answer.
 *
 * @param outcome The answer
 * @return Its string resource
 */
internal fun ownerOutcomeText(outcome: EnquiryOutcome): Int =
    when (outcome) {
        EnquiryOutcome.ADDED -> R.string.hub_enquiry_answered_added
        EnquiryOutcome.NOT_NOW -> R.string.hub_enquiry_answered_not_now
        EnquiryOutcome.CALL_US -> R.string.hub_enquiry_answered_call_us
    }

/**
 * A class level in the listing editor's words.
 *
 * @param wire The server's value
 * @return The words, or an empty string for a level this version does not know
 */
@Composable
internal fun levelText(wire: String): String = classLevelOf(wire)?.let { stringResource(levelLabel(it)) }.orEmpty()
