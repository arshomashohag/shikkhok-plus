package com.shikkhokplus.app.feature.invitations.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.model.AcceptanceState
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.invitations.DeclineSheet
import com.shikkhokplus.app.feature.invitations.InvitationRow
import com.shikkhokplus.app.feature.invitations.InvitationsUiState

/** Test tag for the list of unaccepted seats. */
const val TAG_INVITATION_LIST: String = "invitation_list"

/** Test tag for the accept control on a seat. */
const val TAG_INVITATION_ACCEPT: String = "invitation_accept"

/** Test tag for the decline control on a seat. */
const val TAG_INVITATION_DECLINE: String = "invitation_decline"

/** Test tag for the decline confirmation sheet. */
const val TAG_DECLINE_SHEET: String = "decline_sheet"

/**
 * `O4`, invitations, in its seven states.
 *
 * **Three fields and no more** [BR1.4, AC1.10.1]. A seat rendered here
 * shows its batch name, its subjects and its fee. It shows no
 * attendance, no marks, no other enrollment and no write action but
 * accept and decline — which this screen can honour because
 * [InvitationRow] carries nothing else to render. The invitation lens
 * is scoped to one enrollment and the response schema carries those
 * fields alone, so there is nothing here to leak.
 *
 * **A declined seat stays listed** [BR5.4, BR5.5, AC1.13.1]. Declining
 * is durable against the teacher and reversible by its holder, so the
 * seat leaves the person's enrollments and remains among their
 * invitations with an accept action. Dropping it from this list would
 * make the reversal unreachable.
 *
 * @param state What to render
 * @param onOpen Called to open one seat in detail
 * @param onAccept Called with the enrollment id being accepted
 * @param onDeclineRequested Called to open the confirmation sheet
 * @param onDeclineConfirmed Called with the enrollment id to decline
 * @param onDismissSheet Called when the sheet is dismissed
 * @param onRetry Called when a retryable failure offers a retry
 * @param modifier Layout modifier from the caller
 */
@Composable
fun InvitationsScreen(
    state: InvitationsUiState,
    onOpen: (String) -> Unit,
    onAccept: (String) -> Unit,
    onDeclineRequested: (String) -> Unit,
    onDeclineConfirmed: (String) -> Unit,
    onDismissSheet: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = stringResource(R.string.invitations_title),
            style = MaterialTheme.typography.headlineSmall,
        )

        when (state) {
            InvitationsUiState.Idle,
            InvitationsUiState.Loading,
            -> CircularProgressIndicator()

            InvitationsUiState.Empty -> {
                Text(
                    text = stringResource(R.string.invitations_empty_title),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(text = stringResource(R.string.invitations_empty_body))
            }

            is InvitationsUiState.Loaded -> LazyColumn(
                modifier = Modifier.fillMaxWidth().testTag(TAG_INVITATION_LIST),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(state.rows, key = { it.enrollmentId }) { row ->
                    InvitationCard(
                        row = row,
                        onOpen = { onOpen(row.enrollmentId) },
                        onAccept = { onAccept(row.enrollmentId) },
                        onDecline = { onDeclineRequested(row.enrollmentId) },
                    )
                }
            }

            is InvitationsUiState.Detail -> InvitationCard(
                row = state.row,
                onOpen = null,
                onAccept = { onAccept(state.row.enrollmentId) },
                onDecline = { onDeclineRequested(state.row.enrollmentId) },
            )

            is InvitationsUiState.ConfirmingDecline -> DeclineConfirmation(
                sheet = state.sheet,
                batchName = state.row.batchName,
                onConfirm = { onDeclineConfirmed(state.row.enrollmentId) },
                onDismiss = onDismissSheet,
            )

            is InvitationsUiState.Decided -> Text(
                text = stringResource(
                    R.string.invitation_accepted_confirmation,
                ),
            )

            is InvitationsUiState.Failed -> {
                Text(
                    text = stringResource(R.string.invitations_error_title),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = stringResource(
                        MessageKeys.resolve(state.messageKey),
                    ),
                    color = MaterialTheme.colorScheme.error,
                )
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(stringResource(R.string.auth_retry))
                    }
                }
            }
        }
    }
}

/**
 * One seat, with its two actions.
 *
 * The fee is rendered from [com.shikkhokplus.app.core.model.Money] at
 * the last possible moment, so no intermediate layer turns it into a
 * number [TC-7, D-20]. A null fee means the seat inherits the batch
 * default, which is **not** the same as zero: zero is a waiver.
 *
 * @param row The seat
 * @param onOpen Called when the card is opened, or null when this card
 *   is already the detail view and has nothing further to open. A null
 *   here renders a non-clickable card rather than one that announces
 *   itself as actionable and then does nothing [AC9.4.2]
 * @param onAccept Called when accepted
 * @param onDecline Called when decline is requested
 */
@Composable
private fun InvitationCard(
    row: InvitationRow,
    onOpen: (() -> Unit)?,
    onAccept: () -> Unit,
    onDecline: () -> Unit,
) {
    val content: @Composable () -> Unit = {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = row.batchName,
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text = stringResource(R.string.invitation_subject_label),
                style = MaterialTheme.typography.labelMedium,
            )
            Text(text = row.subject.joinToString(", "))
            row.fee?.let { fee ->
                Text(
                    text = stringResource(
                        R.string.invitation_fee_per_month,
                        fee.toString(),
                    ),
                )
            }
            Text(text = stringResource(stateLabelOf(row.state)))

            Button(
                onClick = onAccept,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag(TAG_INVITATION_ACCEPT),
            ) {
                Text(stringResource(R.string.invitation_accept))
            }
            if (row.canDecline) {
                OutlinedButton(
                    onClick = onDecline,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag(TAG_INVITATION_DECLINE),
                ) {
                    Text(stringResource(R.string.invitation_decline))
                }
            }
        }
    }

    if (onOpen == null) {
        Card(modifier = Modifier.fillMaxWidth()) { content() }
    } else {
        Card(modifier = Modifier.fillMaxWidth(), onClick = onOpen) {
            content()
        }
    }
}

/**
 * The decline confirmation, in the wording this role must read.
 *
 * **Two sheets, never one** [BR5.2, AC1.14.1a]. A single confirmation
 * written once and shown to both roles told a guardian a debt was
 * cancelled when it was not: a guardian's decline withdraws the
 * guardian's own lens and leaves the student's obligation entirely
 * intact. The `when` is exhaustive over [DeclineSheet], so a third
 * role would fail to compile here rather than silently reuse one of
 * these two.
 *
 * @param sheet Which confirmation to show
 * @param batchName The class being declined, named in both bodies so
 *   the person can see which seat this is
 * @param onConfirm Called when the decline is confirmed
 * @param onDismiss Called when the sheet is dismissed
 */
@Composable
private fun DeclineConfirmation(
    sheet: DeclineSheet,
    batchName: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    val titleRes = when (sheet) {
        DeclineSheet.STUDENT -> R.string.decline_student_title
        DeclineSheet.GUARDIAN -> R.string.decline_guardian_title
    }
    val bodyRes = when (sheet) {
        DeclineSheet.STUDENT -> R.string.decline_student_body
        DeclineSheet.GUARDIAN -> R.string.decline_guardian_body
    }

    Column(
        modifier = Modifier.fillMaxWidth().testTag(TAG_DECLINE_SHEET),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = stringResource(titleRes),
            style = MaterialTheme.typography.titleMedium,
        )
        Text(text = stringResource(bodyRes, batchName))
        Button(onClick = onConfirm, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.decline_confirm))
        }
        OutlinedButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.action_cancel))
        }
    }
}

/**
 * The string resource naming a seat's own decision state.
 *
 * Only `PENDING` and `DECLINED` reach this screen: an accepted seat has
 * left the invitation list for the person's enrollments [BR5.5]. The
 * `when` is still exhaustive so the compiler, not a reader, enforces
 * that.
 *
 * @param state This holder's own decision
 * @return Its string resource id
 */
private fun stateLabelOf(state: AcceptanceState): Int = when (state) {
    AcceptanceState.PENDING -> R.string.invitation_state_pending
    AcceptanceState.DECLINED -> R.string.invitation_state_declined
    AcceptanceState.ACCEPTED -> R.string.invitation_accepted_confirmation
}
