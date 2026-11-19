package com.shikkhokplus.app.feature.hubreviews.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthYear
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hubreviews.OwnerBatchRating
import com.shikkhokplus.app.feature.hubreviews.OwnerReviewsContent
import com.shikkhokplus.app.feature.hubreviews.OwnerReviewsUiState
import com.shikkhokplus.app.feature.hubreviews.RATING_MAX
import com.shikkhokplus.app.feature.hubreviews.REVIEW_TEXT_MAX
import com.shikkhokplus.app.feature.hubreviews.RatingLine
import com.shikkhokplus.app.feature.hubreviews.ReplyCard
import com.shikkhokplus.app.feature.hubreviews.WriteKind
import com.shikkhokplus.app.feature.hubreviews.ratingLine

/** The reply delete confirmation's Delete button. */
const val TAG_REPLY_DELETE_CONFIRM: String = "hub_reply_delete_confirm"

/**
 * Tag for a review's reply box.
 *
 * @param reviewId The review
 * @return The tag
 */
fun replyFieldTag(reviewId: String): String = "hub_reply_field_$reviewId"

/**
 * Tag for a review's Send reply.
 *
 * @param reviewId The review
 * @return The tag
 */
fun replySendTag(reviewId: String): String = "hub_reply_send_$reviewId"

/**
 * Tag for a review's Delete reply.
 *
 * @param reviewId The review
 * @return The tag
 */
fun replyDeleteTag(reviewId: String): String = "hub_reply_delete_$reviewId"

/**
 * Tag for a review's Report.
 *
 * @param reviewId The review
 * @return The tag
 */
fun replyReportTag(reviewId: String): String = "hub_reply_report_$reviewId"

/**
 * What the owner's Reviews screen can do, each by review id.
 *
 * @property onReply Changes a reply as typed
 * @property onSend Sends a reply
 * @property onDelete Opens a reply's delete confirmation
 * @property onConfirmDelete Deletes it
 * @property onCancelDelete Closes the confirmation
 * @property onRetry Repeats a review's failed write
 * @property onReport Reports a review
 * @property onRetryLoad Reads again
 * @property onDismissNotice Forgets the "reply deleted" confirmation
 * @property onBack Leaves the screen
 */
data class OwnerReviewsActions(
    val onReply: (String, String) -> Unit = { _, _ -> },
    val onSend: (String) -> Unit = {},
    val onDelete: (String) -> Unit = {},
    val onConfirmDelete: (String) -> Unit = {},
    val onCancelDelete: (String) -> Unit = {},
    val onRetry: (String) -> Unit = {},
    val onReport: (String) -> Unit = {},
    val onRetryLoad: () -> Unit = {},
    val onDismissNotice: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The owner's Reviews screen [H4]: each published batch's rating, then
 * the published reviews, newest month first as the server sends them,
 * each with a reply box.
 *
 * **Exactly what the public sees, and no more.** Below three published
 * reviews a batch's figures arrive as nulls and the row shows a neutral
 * line, never a number; the average is the server's `average_label`,
 * shown as sent [F13]. A review shows a tenure and a month, never a name.
 * `HUB_REVIEWS_OFF` draws nothing at all, and no error.
 *
 * @param state What to render
 * @param actions What the controls do
 * @param modifier Layout modifier from the caller
 */
@Composable
fun OwnerReviewsScreen(
    state: OwnerReviewsUiState,
    actions: OwnerReviewsActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.hub_reviews_title), modifier = modifier, onBack = actions.onBack) {
        when (state) {
            OwnerReviewsUiState.Loading -> SkeletonList(rows = 4)
            is OwnerReviewsUiState.Error ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) actions.onRetryLoad else null,
                )
            OwnerReviewsUiState.Off -> Unit
            is OwnerReviewsUiState.Ready -> Content(state.content, busy = null, actions)
            is OwnerReviewsUiState.Saving -> Content(state.content, busy = state.reviewId, actions)
        }
    }
    val confirming =
        (state as? OwnerReviewsUiState.Ready)?.content?.cards?.firstOrNull { it.confirmingDelete }
    if (confirming != null) {
        val id = confirming.review.id
        DeleteDialog(
            title = stringResource(R.string.hub_reviews_reply_delete_title),
            body = stringResource(R.string.hub_reviews_reply_delete_body),
            confirm = stringResource(R.string.hub_reviews_reply_delete),
            confirmTag = TAG_REPLY_DELETE_CONFIRM,
            onConfirm = { actions.onConfirmDelete(id) },
            onCancel = { actions.onCancelDelete(id) },
        )
    }
}

/**
 * The rating rows, then the reviews.
 *
 * @param content The page
 * @param busy The review whose reply is in flight, or null
 * @param actions What the controls do
 */
@Composable
private fun Content(content: OwnerReviewsContent, busy: String?, actions: OwnerReviewsActions) {
    if (content.replyDeleted) Notice(stringResource(R.string.hub_reviews_reply_deleted), actions.onDismissNotice)
    content.batches.forEach { BatchRating(it) }
    Text(
        stringResource(R.string.hub_reviews_published_heading),
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.asHeading(),
    )
    if (content.cards.isEmpty()) {
        ShikkhokCard { Quiet(stringResource(R.string.hub_reviews_none)) }
    } else {
        content.cards.forEach { card ->
            ReviewCard(card, content.titleOf(card.review.batchId).orEmpty(), busy != null, actions)
        }
    }
}

/**
 * One batch's rating: the server's label, its count and distribution, or
 * the neutral line below the threshold.
 *
 * @param rating The server's row
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BatchRating(rating: OwnerBatchRating) {
    ShikkhokCard {
        Text(Numerals.freeText(rating.batchTitle.orEmpty()), style = MaterialTheme.typography.titleMedium)
        when (val line = rating.ratingLine()) {
            RatingLine.BelowThreshold -> Quiet(stringResource(R.string.hub_reviews_below_threshold))
            is RatingLine.Shown -> {
                Text(
                    stringResource(R.string.hub_reviews_average, line.averageLabel),
                    style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold),
                )
                line.count?.let { Quiet(pluralStringResource(R.plurals.hub_reviews_count, it, it)) }
                line.distribution?.let { stars ->
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        for (star in RATING_MAX downTo 1) {
                            val count = stars.getOrElse(star - 1) { 0 }
                            Quiet(stringResource(R.string.hub_reviews_distribution, star, count))
                        }
                    }
                }
            }
        }
    }
}

/**
 * One published review: stars, tenure and month, the words, and the
 * owner's reply box with its status.
 *
 * @param card The review and its reply box
 * @param batchTitle The batch's public title
 * @param busy Whether any reply is in flight
 * @param actions What the controls do
 */
@Composable
private fun ReviewCard(card: ReplyCard, batchTitle: String, busy: Boolean, actions: OwnerReviewsActions) {
    val review = card.review
    val id = review.id
    ShikkhokCard {
        Text(Numerals.freeText(batchTitle), style = MaterialTheme.typography.titleMedium)
        RatingStars(review.rating)
        Quiet(listOfNotNull(tenureText(review.tenure), monthYear(review.publishedMonth)).joinToString(" · "))
        review.body?.let { Text(Numerals.freeText(it), style = MaterialTheme.typography.bodyLarge) }
        ShikkhokTextField(
            value = card.draft,
            onValueChange = { actions.onReply(id, it) },
            label = stringResource(R.string.hub_reviews_reply_label),
            help =
                stringResource(R.string.hub_reviews_reply_note) + "  " +
                    countText(card.draft.length, REVIEW_TEXT_MAX),
            enabled = !busy,
            singleLine = false,
            minLines = 3,
            fieldModifier = Modifier.testTag(replyFieldTag(id)),
        )
        review.myReplyStatus?.let { status ->
            statusText(status, review.myReplyRejectionCode)?.let {
                Text(it, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            }
        }
        card.failure?.let { failure ->
            WriteFailed(
                prefix =
                    stringResource(
                        if (failure.kind == WriteKind.DELETE) {
                            R.string.hub_reviews_reply_delete_failed
                        } else {
                            R.string.hub_reviews_reply_failed
                        },
                    ),
                failure = failure,
                onRetry = { actions.onRetry(id) },
                retryTag = "hub_reply_retry_$id",
            )
        }
        SecondaryButton(
            text = stringResource(R.string.hub_reviews_reply_send),
            onClick = { actions.onSend(id) },
            modifier = Modifier.fillMaxWidth().testTag(replySendTag(id)),
            enabled = !busy && card.draft.isNotBlank(),
        )
        if (review.myReplyStatus != null) {
            TextAction(
                stringResource(R.string.hub_reviews_reply_delete),
                { actions.onDelete(id) },
                Modifier.fillMaxWidth().testTag(replyDeleteTag(id)),
                enabled = !busy,
            )
        }
        TextAction(
            stringResource(R.string.hub_reviews_report),
            { actions.onReport(id) },
            Modifier.fillMaxWidth().testTag(replyReportTag(id)),
        )
    }
}
