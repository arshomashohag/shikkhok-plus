package com.shikkhokplus.app.feature.roster.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.roster.RemovalRemedy
import com.shikkhokplus.app.feature.roster.RosterRow

/**
 * Confirm removing a seat [W4].
 *
 * **Names what is being removed.** A confirmation asking "are you
 * sure?" about nothing in particular is one a teacher clicks through,
 * and the seat it removes is whichever one they last tapped.
 *
 * The label is `displayLabel`, not `displayName` — the mapper already
 * chose the number for a declined seat [BR2.3], and a declined seat is
 * the commonest thing being removed here, since the mistyped number is
 * exactly what this path exists to recover from [AC2.5.1a].
 *
 * A null label means a declined seat with no number recorded, and the
 * placeholder stands in. BR2.3 forbids showing the name of someone who
 * has declined, and a removal confirmation is the worst place to make
 * an exception: it names a person to confirm an action against them.
 *
 * @param row The seat being removed
 * @param onConfirm Called when the teacher confirms
 * @param onCancel Called when the teacher backs out
 * @param modifier The layout modifier
 */
@Composable
fun RemoveSeatConfirm(
    row: RosterRow,
    onConfirm: (RosterRow) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().testTag(TAG_ROSTER_REMOVE_CONFIRM),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            stringResource(R.string.roster_remove_confirm_title),
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            stringResource(
                R.string.roster_remove_confirm_body,
                row.displayLabel?.let { Numerals.freeText(it) }
                    ?: stringResource(R.string.roster_declined_no_number),
            ),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { onConfirm(row) }) {
                Text(stringResource(R.string.roster_remove_confirm))
            }
            TextButton(onClick = onCancel) {
                Text(stringResource(R.string.action_cancel))
            }
        }
    }
}

/**
 * Explain a refused removal, and offer the remedy that applies [BR3.2].
 *
 * **Two refusals, two remedies, and neither offers a retry.** The
 * server returns distinct codes because the remedies genuinely differ:
 * a claimed seat can be marked inactive and its record stands
 * [ADR-003, FR1.9i]; an erased one cannot be reused at all, because
 * deleting the row would destroy the marker that stops that number
 * reattaching [BR6.2]. One message for both leaves a teacher trying the
 * one that cannot work.
 *
 * The remedy was chosen by `RosterStateMapper`; this renders it. The
 * `when` is exhaustive, so a third refusal fails to compile rather than
 * silently showing one of these two.
 *
 * Neither branch draws a retry: both refusals are conflicts, so
 * repeating the request unchanged cannot succeed.
 *
 * @param row The seat that was not removed
 * @param remedy What the teacher can do instead
 * @param onMarkInactive Called when the teacher takes the remedy
 * @param onDismiss Called when the teacher closes the message
 * @param modifier The layout modifier
 */
@Composable
fun RemoveSeatRefused(
    row: RosterRow,
    remedy: RemovalRemedy,
    onMarkInactive: (RosterRow) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().testTag(TAG_ROSTER_REMOVE_REFUSED),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            stringResource(R.string.roster_remove_refused_title),
            style = MaterialTheme.typography.titleMedium,
        )
        val remedyText = when (remedy) {
            RemovalRemedy.MARK_INACTIVE ->
                stringResource(R.string.roster_remove_claimed_remedy)
            RemovalRemedy.NONE ->
                stringResource(R.string.roster_remove_erased_remedy)
        }
        Text(remedyText, Modifier.testTag(TAG_ROSTER_REMEDY))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            // The ACTION exists only where there is a remedy. An erased
            // seat gets no button, because offering one that cannot
            // help is the failure this was split in two to prevent.
            when (remedy) {
                RemovalRemedy.MARK_INACTIVE ->
                    Button(
                        onClick = { onMarkInactive(row) },
                        modifier = Modifier.testTag(TAG_ROSTER_MARK_INACTIVE),
                    ) {
                        Text(stringResource(R.string.roster_mark_inactive))
                    }
                RemovalRemedy.NONE -> Unit
            }
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.action_close))
            }
        }
    }
}
