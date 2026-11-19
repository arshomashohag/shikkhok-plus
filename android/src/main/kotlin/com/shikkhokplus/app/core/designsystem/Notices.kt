package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import kotlinx.coroutines.delay

/** How long a short confirmation ([Notice]) stays up. */
private const val NOTICE_MILLIS: Long = 3_000

/**
 * A secondary line, in the muted colour.
 *
 * @param text The line
 * @param small Whether it is drawn a step smaller, as the family screens draw their meta lines
 */
@Composable
fun Quiet(text: String, small: Boolean = false) {
    Text(
        text,
        style = if (small) MaterialTheme.typography.bodySmall else MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/**
 * A short confirmation that goes after a few seconds.
 *
 * @param text The confirmation
 * @param onDismiss Forgets it
 */
@Composable
fun Notice(text: String, onDismiss: () -> Unit) {
    LaunchedEffect(text) {
        delay(NOTICE_MILLIS)
        onDismiss()
    }
    Banner(title = text, tone = BannerTone.INFO)
}

/**
 * A delete confirmation; nothing is deleted from anywhere else.
 *
 * @param title The question
 * @param body What deleting does
 * @param confirm The confirming button's label
 * @param confirmTag Its tag
 * @param onConfirm Deletes
 * @param onCancel Closes without deleting
 */
@Composable
fun DeleteDialog(
    title: String,
    body: String,
    confirm: String,
    confirmTag: String,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text(title) },
        text = { Text(body) },
        confirmButton = { TextAction(confirm, onConfirm, Modifier.testTag(confirmTag)) },
        dismissButton = { TextAction(stringResource(R.string.action_cancel), onCancel) },
    )
}
