package com.shikkhokplus.app.feature.hubreviews.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.LocalTouchScale
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayMonthYear
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hubreviews.RATING_MAX
import com.shikkhokplus.app.feature.hubreviews.REVIEW_TEXT_MAX
import com.shikkhokplus.app.feature.hubreviews.ReviewEditorUiState
import com.shikkhokplus.app.feature.hubreviews.ReviewForm
import com.shikkhokplus.app.feature.hubreviews.WriteKind

/** The words field. */
const val TAG_REVIEW_BODY: String = "hub_review_body"

/** Submit, or Save changes. */
const val TAG_REVIEW_SAVE: String = "hub_review_save"

/** Delete review. */
const val TAG_REVIEW_DELETE: String = "hub_review_delete"

/** The delete confirmation's Delete button. */
const val TAG_REVIEW_DELETE_CONFIRM: String = "hub_review_delete_confirm"

/** Retry after a failed write. */
const val TAG_REVIEW_RETRY: String = "hub_review_retry"

/**
 * Tag for one rating's row.
 *
 * @param rating 1 to 5
 * @return The tag
 */
fun reviewStarTag(rating: Int): String = "hub_review_star_$rating"

/**
 * What the review editor can do.
 *
 * @property onRating Chooses a rating
 * @property onText Changes the words
 * @property onSave Submits, or saves the edit
 * @property onDelete Opens the delete confirmation
 * @property onConfirmDelete Deletes
 * @property onCancelDelete Closes the confirmation
 * @property onRetry Repeats the write that failed
 * @property onRetryLoad Reads again
 * @property onDismissNotice Forgets the "deleted" confirmation
 * @property onBack Leaves the screen
 */
data class ReviewEditorActions(
    val onRating: (Int) -> Unit = {},
    val onText: (String) -> Unit = {},
    val onSave: () -> Unit = {},
    val onDelete: () -> Unit = {},
    val onConfirmDelete: () -> Unit = {},
    val onCancelDelete: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onRetryLoad: () -> Unit = {},
    val onDismissNotice: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * One batch's review, as its guardian author sees it [H4].
 *
 * **The server decides; the screen draws.** `can_write` alone says
 * whether the form is editable, `edit_until` is the last day an edit is
 * accepted, `standing` says why a member cannot write yet, and `status`
 * with `rejection_code` says where the review is in moderation. A failed
 * write keeps the rating and the words [TC-8]. Delete is offered for any
 * review, editable or not.
 *
 * @param state What to render
 * @param title The batch's public title, when the opener knew it
 * @param actions What the controls do
 * @param modifier Layout modifier from the caller
 */
@Composable
fun ReviewEditorScreen(
    state: ReviewEditorUiState,
    title: String?,
    actions: ReviewEditorActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.hub_review_editor_title),
        subtitle = title?.ifBlank { null }?.let(Numerals::freeText),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        when (state) {
            ReviewEditorUiState.Loading -> SkeletonList(rows = 3)
            is ReviewEditorUiState.Error ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) actions.onRetryLoad else null,
                )
            ReviewEditorUiState.Off -> Unit
            is ReviewEditorUiState.Ready -> Editor(state.form, busy = false, actions)
            is ReviewEditorUiState.Saving -> Editor(state.form, busy = true, actions)
        }
    }
    val form = (state as? ReviewEditorUiState.Ready)?.form
    if (form?.confirmingDelete == true) {
        DeleteDialog(
            title = stringResource(R.string.hub_review_delete_title),
            body = stringResource(R.string.hub_review_delete_body),
            confirm = stringResource(R.string.hub_review_delete),
            confirmTag = TAG_REVIEW_DELETE_CONFIRM,
            onConfirm = actions.onConfirmDelete,
            onCancel = actions.onCancelDelete,
        )
    }
}

/**
 * The editor: the standing note, the review as it stands, the form while
 * writable, the teacher's reply, and Delete.
 *
 * @param form What is shown and typed
 * @param busy Whether a write is in flight
 * @param actions What the controls do
 */
@Composable
private fun Editor(form: ReviewForm, busy: Boolean, actions: ReviewEditorActions) {
    if (form.deleted) Notice(stringResource(R.string.hub_review_deleted), actions.onDismissNotice)
    form.note?.let { note ->
        Banner(
            title = stringResource(MessageKeys.resolve(note.messageKey)),
            body = note.eligibleFrom?.let { stringResource(R.string.hub_review_eligible_from, dayMonthYear(it)) },
            tone = BannerTone.INFO,
        )
    }
    val review = form.review.review
    if (review != null) {
        ShikkhokCard {
            statusText(review.status, review.rejectionCode)?.let {
                Text(it, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
            }
            tenureText(review.tenure)?.let { Quiet(it) }
            form.review.editUntil?.let { Quiet(stringResource(R.string.hub_review_edit_until, dayMonthYear(it))) }
            if (!form.review.canWrite) {
                RatingStars(review.rating)
                review.body?.let { Text(Numerals.freeText(it), style = MaterialTheme.typography.bodyLarge) }
            }
        }
    }
    if (form.review.canWrite) WriteForm(form, busy, actions) else Failure(form, actions)
    review?.replyBody?.let { reply ->
        Text(
            stringResource(R.string.hub_review_reply_heading),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.asHeading(),
        )
        ShikkhokCard { Text(Numerals.freeText(reply), style = MaterialTheme.typography.bodyLarge) }
    }
    if (review != null) {
        TextAction(
            stringResource(R.string.hub_review_delete),
            actions.onDelete,
            Modifier.fillMaxWidth().testTag(TAG_REVIEW_DELETE),
            enabled = !busy,
        )
    }
}

/**
 * The five labelled ratings, the words with their count, the privacy
 * note, and Submit or Save.
 *
 * @param form What is shown and typed
 * @param busy Whether a write is in flight
 * @param actions What the controls do
 */
@Composable
private fun WriteForm(form: ReviewForm, busy: Boolean, actions: ReviewEditorActions) {
    Text(
        stringResource(R.string.hub_review_rating_legend),
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.asHeading(),
    )
    Column(Modifier.fillMaxWidth().selectableGroup()) {
        for (rating in 1..RATING_MAX) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = LocalTouchScale.current.rowSingle)
                    .selectable(
                        selected = form.rating == rating,
                        enabled = !busy,
                        role = Role.RadioButton,
                        onClick = { actions.onRating(rating) },
                    ).padding(horizontal = 4.dp)
                    .testTag(reviewStarTag(rating)),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RadioButton(selected = form.rating == rating, onClick = null, enabled = !busy)
                Text(
                    stringResource(starLabel(rating)),
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(start = 12.dp).weight(1f),
                )
            }
        }
    }
    ShikkhokTextField(
        value = form.text,
        onValueChange = actions.onText,
        label = stringResource(R.string.hub_review_body_label),
        help = countText(form.text.length, REVIEW_TEXT_MAX),
        enabled = !busy,
        singleLine = false,
        minLines = 5,
        fieldModifier = Modifier.testTag(TAG_REVIEW_BODY),
    )
    Quiet(stringResource(R.string.hub_review_privacy_note))
    Failure(form, actions)
    PrimaryButton(
        text = stringResource(if (form.review.review != null) R.string.hub_review_save else R.string.hub_review_submit),
        onClick = actions.onSave,
        modifier = Modifier.fillMaxWidth().testTag(TAG_REVIEW_SAVE),
        enabled = form.canSave && !busy,
    )
}

/**
 * The last write's failure, if any.
 *
 * @param form What is shown
 * @param actions What Retry does
 */
@Composable
private fun Failure(form: ReviewForm, actions: ReviewEditorActions) {
    val failure = form.failure ?: return
    WriteFailed(
        prefix =
            stringResource(
                if (failure.kind == WriteKind.DELETE) R.string.hub_review_delete_failed else R.string.hub_review_failed,
            ),
        failure = failure,
        onRetry = actions.onRetry,
        retryTag = TAG_REVIEW_RETRY,
    )
}

/**
 * A rating's label: "4 stars · Very good".
 *
 * @param rating 1 to 5
 * @return Its string resource
 */
private fun starLabel(rating: Int): Int =
    when (rating) {
        1 -> R.string.hub_review_star_1
        2 -> R.string.hub_review_star_2
        3 -> R.string.hub_review_star_3
        4 -> R.string.hub_review_star_4
        else -> R.string.hub_review_star_5
    }
