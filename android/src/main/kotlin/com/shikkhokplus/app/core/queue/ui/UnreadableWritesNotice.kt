package com.shikkhokplus.app.core.queue.ui

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.queue.QueueStore

/** The notice that unsent records could not be read. */
const val TAG_QUEUE_UNREADABLE: String = "queue_unreadable"

/** Its acknowledgement. */
const val TAG_QUEUE_UNREADABLE_OK: String = "queue_unreadable_ok"

/**
 * Tells the teacher that queued writes on this phone could not be read.
 *
 * **The one place a lost queue is said out loud** [BR3.1, C-46]. A
 * queue file the app cannot open -- its key gone, or the file damaged --
 * holds records the teacher believes are on their way. Starting empty
 * keeps the app usable; this notice keeps the loss from being silent.
 * It stays until acknowledged, across launches, because
 * [QueueStore.hasUnreadableWrites] reads a file set aside on disk.
 *
 * @param queue The device's write queue
 */
@Composable
fun UnreadableWritesNotice(queue: QueueStore) {
    var showing by remember { mutableStateOf(queue.hasUnreadableWrites()) }
    if (!showing) return
    val acknowledge = {
        queue.acknowledgeUnreadableWrites()
        showing = false
    }
    AlertDialog(
        // Dismissing is not acknowledging: the notice returns on the next
        // launch until OK is pressed.
        onDismissRequest = { showing = false },
        modifier = Modifier.testTag(TAG_QUEUE_UNREADABLE),
        title = { Text(stringResource(R.string.queue_unreadable_title)) },
        text = { Text(stringResource(R.string.queue_unreadable_body)) },
        confirmButton = {
            TextAction(
                text = stringResource(R.string.action_ok),
                onClick = acknowledge,
                modifier = Modifier.testTag(TAG_QUEUE_UNREADABLE_OK),
            )
        },
    )
}
