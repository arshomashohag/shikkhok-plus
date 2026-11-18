package com.shikkhokplus.app.feature.hubmedia.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hublisting.ui.FailureBanner
import com.shikkhokplus.app.feature.hublisting.ui.Pill
import com.shikkhokplus.app.feature.hubmedia.HubPhotosState
import com.shikkhokplus.app.feature.hubmedia.MediaResponse
import com.shikkhokplus.app.feature.hubmedia.PhotoUpload

/** The "N of 12 photos" line. */
const val TAG_PHOTOS_COUNT: String = "hub_photos_count"

/** The English alt text field. */
const val TAG_PHOTOS_ALT_EN: String = "hub_photos_alt_en"

/** The Bangla alt text field. */
const val TAG_PHOTOS_ALT_BN: String = "hub_photos_alt_bn"

/** "Add a photo", which opens the photo picker. */
const val TAG_PHOTOS_ADD: String = "hub_photos_add"

/** Retry, or Check again, after a photo was not added. */
const val TAG_PHOTOS_RETRY_UPLOAD: String = "hub_photos_retry_upload"

/** Retry after the gallery could not be read. */
const val TAG_PHOTOS_RETRY_LOAD: String = "hub_photos_retry_load"

/** The delete confirmation's Delete button. */
const val TAG_PHOTO_DELETE_CONFIRM: String = "hub_photo_delete_confirm"

/** Tag for the move-up control of the photo at [index]. */
fun photoMoveUpTag(index: Int): String = "hub_photo_up_$index"

/** Tag for the move-down control of the photo at [index]. */
fun photoMoveDownTag(index: Int): String = "hub_photo_down_$index"

/** Tag for the delete control of the photo at [index]. */
fun photoDeleteTag(index: Int): String = "hub_photo_delete_$index"

/** The placeholder's side. */
private val THUMB = 64.dp

/**
 * What the photos screen's controls call.
 *
 * @property onAltEn Changes the English alt text
 * @property onAltBn Changes the Bangla alt text
 * @property onAdd Opens the photo picker, when a photo may be added
 * @property onRetryUpload Repeats a failed upload, or polls again
 * @property onRetryLoad Reads the gallery again
 * @property onMove Moves the photo at an index by -1 or 1
 * @property onDelete Asks to delete a photo
 * @property onConfirmDelete Deletes it
 * @property onCancelDelete Keeps it
 * @property onRetryWrite Repeats a failed reorder or delete
 * @property onBack Leaves the screen
 */
data class HubPhotosActions(
    val onAltEn: (String) -> Unit = {},
    val onAltBn: (String) -> Unit = {},
    val onAdd: () -> Unit = {},
    val onRetryUpload: () -> Unit = {},
    val onRetryLoad: () -> Unit = {},
    val onMove: (Int, Int) -> Unit = { _, _ -> },
    val onDelete: (MediaResponse) -> Unit = {},
    val onConfirmDelete: () -> Unit = {},
    val onCancelDelete: () -> Unit = {},
    val onRetryWrite: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * One gallery: the owner's own page's, or one batch's [H3].
 *
 * Renders the server's list as it arrives: its order, its statuses, its
 * length against the limit. **No photo is drawn**: the app has no image
 * loader and adds none for this screen, so each photo shows a placeholder,
 * its alt text and its status; the photo itself is seen on the public page.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun HubPhotosScreen(
    state: HubPhotosState,
    actions: HubPhotosActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.hub_photos_title), modifier = modifier, onBack = actions.onBack) {
        if (state.photos != null) {
            Text(
                stringResource(R.string.hub_photos_count, state.count.toString(), state.limit.toString()),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.testTag(TAG_PHOTOS_COUNT),
            )
        }
        Text(
            stringResource(R.string.hub_photos_help),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Gallery(state, actions)
        state.failure?.let { FailureBanner(it, actions.onRetryWrite) }
        if (!state.readOnly) AddPhoto(state, actions)
    }
    state.deleting?.let { DeleteDialog(actions) }
}

@Composable
private fun Gallery(state: HubPhotosState, actions: HubPhotosActions) {
    val failed = state.loadFailure
    val photos = state.photos
    when {
        failed != null ->
            Banner(
                title = stringResource(R.string.hub_photos_load_failed),
                body = stringResource(MessageKeys.resolve(failed.messageKey)),
                tone = BannerTone.ERROR,
                action =
                    if (failed.canRetry) {
                        {
                            TextAction(
                                stringResource(R.string.auth_retry),
                                actions.onRetryLoad,
                                Modifier.testTag(TAG_PHOTOS_RETRY_LOAD),
                            )
                        }
                    } else {
                        null
                    },
            )
        photos == null -> SkeletonList(rows = 2)
        photos.isEmpty() ->
            Text(
                stringResource(R.string.hub_photos_empty),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        else ->
            photos.forEachIndexed { index, photo ->
                PhotoRow(photo, index, last = index == photos.lastIndex, state, actions)
            }
    }
}

@Composable
private fun PhotoRow(
    photo: MediaResponse,
    index: Int,
    last: Boolean,
    state: HubPhotosState,
    actions: HubPhotosActions,
) {
    val bangla = LocalConfiguration.current.locales[0].language == "bn"
    val alt = (if (bangla) photo.altBn ?: photo.altEn else photo.altEn ?: photo.altBn).orEmpty()
    val number = (index + 1).toString()
    ShikkhokCard {
        Row(
            Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Spacing.tight),
        ) {
            Placeholder(hasPreview = photo.thumbUrl != null)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (alt.isNotEmpty()) Text(alt, style = MaterialTheme.typography.bodyLarge)
                Pill(stringResource(photoStatusLabel(photo.status)))
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
            // A read-only (suspended) gallery still deletes: the photo keeps
            // its public link until its owner removes it.
            if (!state.readOnly) {
                Control(
                    symbol = "↑",
                    label = stringResource(R.string.hub_photo_move_up, number),
                    tag = photoMoveUpTag(index),
                    enabled = !state.busy && index > 0,
                ) { actions.onMove(index, -1) }
                Control(
                    symbol = "↓",
                    label = stringResource(R.string.hub_photo_move_down, number),
                    tag = photoMoveDownTag(index),
                    enabled = !state.busy && !last,
                ) { actions.onMove(index, 1) }
            }
            Control(
                symbol = "×",
                label = stringResource(R.string.hub_photo_delete, number),
                tag = photoDeleteTag(index),
                enabled = !state.busy,
            ) { actions.onDelete(photo) }
        }
    }
}

/**
 * Where the photo would be drawn. "No preview" when the server has no
 * preview for it (rejected, withdrawn, or not yet read).
 */
@Composable
private fun Placeholder(hasPreview: Boolean) {
    Box(
        Modifier.size(THUMB).background(MaterialTheme.colorScheme.surfaceContainerHigh, MaterialTheme.shapes.small),
        contentAlignment = Alignment.Center,
    ) {
        if (!hasPreview) {
            Text(
                stringResource(R.string.hub_photo_no_preview),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
    }
}

/** A one-symbol control that TalkBack reads by its [label]. */
@Composable
private fun Control(symbol: String, label: String, tag: String, enabled: Boolean, onClick: () -> Unit) {
    TextAction(
        symbol,
        onClick,
        Modifier.testTag(tag).semantics { contentDescription = label },
        enabled = enabled,
    )
}

@Composable
private fun AddPhoto(state: HubPhotosState, actions: HubPhotosActions) {
    val open = !state.inFlight
    ShikkhokTextField(
        value = state.altEn,
        onValueChange = actions.onAltEn,
        label = stringResource(R.string.hub_photo_alt_en),
        enabled = open,
        fieldModifier = Modifier.testTag(TAG_PHOTOS_ALT_EN),
    )
    ShikkhokTextField(
        value = state.altBn,
        onValueChange = actions.onAltBn,
        label = stringResource(R.string.hub_photo_alt_bn),
        enabled = open,
        fieldModifier = Modifier.testTag(TAG_PHOTOS_ALT_BN),
    )
    PrimaryButton(
        text = stringResource(R.string.hub_photo_choose),
        onClick = actions.onAdd,
        enabled = open,
        modifier = Modifier.fillMaxWidth().testTag(TAG_PHOTOS_ADD),
    )
    when (val upload = state.upload) {
        PhotoUpload.Uploading -> Progress(R.string.hub_photo_uploading)
        PhotoUpload.WaitingReview -> Progress(R.string.hub_photo_checking)
        PhotoUpload.Done -> Progress(R.string.hub_photo_sent)
        is PhotoUpload.Failed -> UploadFailed(upload, state.checkAgain, actions.onRetryUpload)
        PhotoUpload.Idle, PhotoUpload.Picking -> Unit
    }
}

@Composable
private fun Progress(text: Int) {
    Text(
        stringResource(text),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/** The server's words for why the photo was not added, with Retry or Check again when it can help. */
@Composable
private fun UploadFailed(failed: PhotoUpload.Failed, checkAgain: Boolean, onRetry: () -> Unit) {
    val message = stringResource(MessageKeys.resolve(failed.failure.messageKey))
    Banner(
        title = if (failed.slow) stringResource(R.string.hub_photo_slow) + " " + message else message,
        tone = BannerTone.ERROR,
        action =
            if (failed.failure.canRetry) {
                {
                    TextAction(
                        stringResource(if (checkAgain) R.string.hub_photo_check_again else R.string.auth_retry),
                        onRetry,
                        Modifier.testTag(TAG_PHOTOS_RETRY_UPLOAD),
                    )
                }
            } else {
                null
            },
    )
}

@Composable
private fun DeleteDialog(actions: HubPhotosActions) {
    AlertDialog(
        onDismissRequest = actions.onCancelDelete,
        title = { Text(stringResource(R.string.hub_photo_delete_title)) },
        text = { Text(stringResource(R.string.hub_photo_delete_body)) },
        confirmButton = {
            TextAction(
                stringResource(R.string.hub_photo_delete_confirm),
                actions.onConfirmDelete,
                Modifier.testTag(TAG_PHOTO_DELETE_CONFIRM),
            )
        },
        dismissButton = { TextAction(stringResource(R.string.action_cancel), actions.onCancelDelete) },
    )
}

/** What a photo's status is called, by the server's word. */
private fun photoStatusLabel(status: String): Int =
    when (status) {
        "awaiting_upload" -> R.string.hub_photo_status_awaiting_upload
        "processing" -> R.string.hub_photo_status_processing
        "pending_review" -> R.string.hub_photo_status_pending_review
        "approved" -> R.string.hub_photo_status_approved
        "rejected" -> R.string.hub_photo_status_rejected
        "held" -> R.string.hub_photo_status_held
        "withdrawn" -> R.string.hub_photo_status_withdrawn
        else -> R.string.error_unexpected
    }
