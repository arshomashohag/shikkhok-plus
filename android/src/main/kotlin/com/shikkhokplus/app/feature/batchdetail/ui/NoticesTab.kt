package com.shikkhokplus.app.feature.batchdetail.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.batchdetail.Notice

/** One notice. */
const val TAG_NOTICE: String = "batch_notice"

/** The notice text field in the compose dialog. */
const val TAG_NOTICE_FIELD: String = "batch_notice_field"

/** The compose dialog's send button. */
const val TAG_NOTICE_SEND: String = "batch_notice_send"

/**
 * The Notices tab: what the teacher told the batch, newest first.
 *
 * @param notices The notices, or null until read
 * @param write A notice being sent, changed or removed
 * @param composing Whether the compose dialog is open
 * @param onCloseCompose Called to close it
 * @param onPost Called with a new notice's text
 * @param onEdit Called with a notice and its new text
 * @param onRemove Called with a notice to take down
 * @param onAcknowledge Called once a write's outcome has been shown
 */
@Composable
fun NoticesTab(
    notices: List<Notice>?,
    write: WriteState,
    composing: Boolean,
    onCloseCompose: () -> Unit,
    onPost: (String) -> Unit,
    onEdit: (Notice, String) -> Unit,
    onRemove: (Notice) -> Unit,
    onAcknowledge: () -> Unit,
) {
    var editing by remember { mutableStateOf<Notice?>(null) }
    var removing by remember { mutableStateOf<Notice?>(null) }

    LaunchedEffect(write) {
        if (write == WriteState.Saved) {
            onAcknowledge()
            if (composing) onCloseCompose()
            editing = null
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        (write as? WriteState.Failed)?.let {
            Banner(stringResource(MessageKeys.resolve(it.messageKey)), tone = BannerTone.ERROR)
        }
        when {
            notices == null -> SkeletonList(rows = 2)
            notices.isEmpty() ->
                EmptyState(
                    stringResource(R.string.batch_notices_empty),
                    stringResource(R.string.batch_notices_empty_body),
                )
            else ->
                LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(notices, key = { it.id }) { notice ->
                        NoticeCard(notice, onEdit = { editing = notice }, onRemove = { removing = notice })
                    }
                    item { Column(Modifier.heightIn(min = 88.dp)) {} }
                }
        }
    }

    if (composing) {
        NoticeDialog(
            initial = "",
            saving = write == WriteState.Saving,
            onSend = onPost,
            onDismiss = onCloseCompose,
        )
    }
    editing?.let { notice ->
        NoticeDialog(
            initial = notice.body,
            saving = write == WriteState.Saving,
            onSend = { onEdit(notice, it) },
            onDismiss = { editing = null },
        )
    }
    removing?.let { notice ->
        AlertDialog(
            onDismissRequest = { removing = null },
            title = { Text(stringResource(R.string.batch_notice_remove_title)) },
            text = { Text(stringResource(R.string.batch_notice_remove_body)) },
            confirmButton = {
                TextButton(onClick = {
                    removing = null
                    onRemove(notice)
                }) { Text(stringResource(R.string.batch_remove), color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { removing = null }) { Text(stringResource(R.string.action_cancel)) }
            },
        )
    }
}

/**
 * One notice, with when it was posted and its two actions.
 *
 * @param notice The notice
 * @param onEdit Called to change it
 * @param onRemove Called to take it down
 */
@Composable
private fun NoticeCard(notice: Notice, onEdit: () -> Unit, onRemove: () -> Unit) {
    ShikkhokCard(Modifier.testTag(TAG_NOTICE)) {
        Text(Numerals.freeText(notice.body), style = MaterialTheme.typography.bodyMedium)
        Text(
            listOfNotNull(
                ago(notice.postedAt),
                stringResource(R.string.batch_notice_edited).takeIf { notice.edited },
            ).joinToString(" · "),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row {
            TextAction(stringResource(R.string.batch_notice_edit), onEdit)
            TextAction(stringResource(R.string.batch_remove), onRemove)
        }
    }
}

/**
 * Write or change a notice.
 *
 * @param initial The text it opens with
 * @param saving Whether a send is in flight
 * @param onSend Called with the text
 * @param onDismiss Called to close without sending
 */
@Composable
private fun NoticeDialog(initial: String, saving: Boolean, onSend: (String) -> Unit, onDismiss: () -> Unit) {
    var text by remember(initial) { mutableStateOf(initial) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.batch_write_notice)) },
        text = {
            ShikkhokTextField(
                value = text,
                onValueChange = { text = it },
                label = stringResource(R.string.batch_notice_label),
                help = stringResource(R.string.batch_notice_help),
                singleLine = false,
                minLines = 3,
                fieldModifier = Modifier.testTag(TAG_NOTICE_FIELD),
            )
        },
        confirmButton = {
            TextButton(
                onClick = { onSend(text) },
                enabled = text.isNotBlank() && !saving,
                modifier = Modifier.testTag(TAG_NOTICE_SEND),
            ) { Text(stringResource(R.string.batch_notice_send)) }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) } },
    )
}
