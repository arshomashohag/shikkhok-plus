package com.shikkhokplus.app.feature.attendance.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.attendance.AttendanceSeat
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/** Stable test identifiers. Not user-visible text. */
const val TAG_ATTENDANCE_LOADING: String = "attendance_loading"

/** The session heading. */
const val TAG_ATTENDANCE_TITLE: String = "attendance_title"

/** The roster. */
const val TAG_ATTENDANCE_LIST: String = "attendance_list"

/** One seat. */
const val TAG_ATTENDANCE_SEAT: String = "attendance_seat"

/** One seat's present toggle. */
const val TAG_ATTENDANCE_TOGGLE: String = "attendance_toggle"

/** The submit action. */
const val TAG_ATTENDANCE_SUBMIT: String = "attendance_submit"

/**
 * The queue badge.
 *
 * **Present whenever a write is pending**, which is what makes "never
 * rendered as confirmed" visible to a test [BR3.1].
 */
const val TAG_ATTENDANCE_QUEUE_BADGE: String = "attendance_queue_badge"

/** The saved-on-phone-not-yet-sent notice. */
const val TAG_ATTENDANCE_QUEUED: String = "attendance_queued"

/** The server-has-it confirmation. */
const val TAG_ATTENDANCE_CONFIRMED: String = "attendance_confirmed"

/** The notice shown when the session accepts no write. */
const val TAG_ATTENDANCE_READ_ONLY: String = "attendance_read_only"

/** The error message. */
const val TAG_ATTENDANCE_ERROR: String = "attendance_error"

/** The retry button, for a FAILED write only. */
const val TAG_ATTENDANCE_RETRY: String = "attendance_retry"

/**
 * The mid-class attendance screen [FR3.5, FR3.6].
 *
 * **This composable renders an [AttendanceUiState] and nothing else.**
 * No conditional here depends on a domain value: the roster's
 * membership is the server's [BR1.5], whether a write is permitted is
 * the server's [BR1.6, BR5.5], and which of the four queue states an
 * item is in was decided before this function was called.
 *
 * **The queued and confirmed states are separate branches of the
 * `when`, not one branch with a flag.** BR3.1 forbids an unsent write
 * ever rendering as confirmed, and separate states are what make that
 * structural rather than a matter of getting a boolean the right way
 * round.
 *
 * **No timing assertion, no latency budget, and no benchmark on this
 * path** [BR7.4]. PU-3.6 was dropped as a requirement at Q14.3 answer C
 * and D4 is not incomplete without one. What stands in its place are
 * two structural properties: a freshly opened roster has every seat
 * present [AC3.1.4], and the roster commits as one write [AC3.1.5].
 *
 * @param state What to render
 * @param onToggle Called with the seat whose mark changed
 * @param onSubmit Called when the teacher commits the roster
 * @param onRetry Called with the failed item the teacher wants resent
 * @param modifier Layout modifier
 */
@Composable
fun AttendanceScreen(
    state: AttendanceUiState,
    onToggle: (AttendanceSeat, Boolean) -> Unit = { _, _ -> },
    onSubmit: () -> Unit = {},
    onRetry: (String) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    ListScreenScaffold(
        title = stringResource(R.string.screen_title_attendance),
        modifier = modifier,
    ) {
        when (state) {
            AttendanceUiState.Idle -> Unit

            AttendanceUiState.Loading ->
                CircularProgressIndicator(Modifier.testTag(TAG_ATTENDANCE_LOADING))

            is AttendanceUiState.Marking -> MarkingBody(state, onToggle, onSubmit)

            is AttendanceUiState.Queued -> {
                // **Saved on this phone, not yet sent.** Never a tick,
                // never the word confirmed [BR3.1]: the server does
                // not have this roster, and the teacher is told so.
                Text(
                    stringResource(
                        R.string.attendance_queued,
                        Numerals.freeText(state.dateLabel),
                    ),
                    Modifier.testTag(TAG_ATTENDANCE_QUEUED),
                )
            }

            is AttendanceUiState.Confirmed ->
                Text(
                    stringResource(R.string.attendance_confirmed),
                    Modifier.testTag(TAG_ATTENDANCE_CONFIRMED),
                )

            // Drawn by `ConflictScreen.kt`. A separate component
            // because it renders two rosters side by side and offers
            // two choices neither of which is a retry [BR3.6].
            is AttendanceUiState.Conflicted -> Unit

            is AttendanceUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_ATTENDANCE_ERROR),
                )
                // **Retry is offered for a failure only**, and only
                // when the server said retryable. A conflict never
                // reaches this branch, because retrying it as-is is
                // guaranteed to be refused again [BR3.6].
                if (state.retryable && state.itemId != null) {
                    Button(
                        onClick = { onRetry(state.itemId) },
                        modifier = Modifier.testTag(TAG_ATTENDANCE_RETRY),
                    ) {
                        Text(stringResource(R.string.attendance_retry))
                    }
                }
            }
        }
    }
}

/**
 * The roster, open for marking.
 *
 * @param state The marking state
 * @param onToggle Called with the seat whose mark changed
 * @param onSubmit Called when the teacher commits
 */
@Composable
private fun MarkingBody(
    state: AttendanceUiState.Marking,
    onToggle: (AttendanceSeat, Boolean) -> Unit,
    onSubmit: () -> Unit,
) {
    Text(
        stringResource(
            R.string.attendance_title,
            Numerals.freeText(state.dateLabel),
        ),
        Modifier.testTag(TAG_ATTENDANCE_TITLE),
    )

    // **The badge is rendered whenever an item is pending**, in
    // whichever of the four states it holds. Its label came from the
    // mapper's exhaustive `when` over QueueState, so a fifth state
    // fails to compile rather than rendering as whichever branch was
    // the fallback -- which for a queue would be a claim about whether
    // the server has the teacher's roster [BR3.2].
    state.queued?.let { badge ->
        Text(
            stringResource(MessageKeys.resolve(badge.labelKey)),
            Modifier.testTag(TAG_ATTENDANCE_QUEUE_BADGE),
        )
    }

    LazyColumn(Modifier.testTag(TAG_ATTENDANCE_LIST)) {
        items(state.seats, key = { it.enrollmentId }) { seat ->
            Row(
                Modifier.fillMaxWidth().testTag(TAG_ATTENDANCE_SEAT),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(Numerals.freeText(seat.displayName))
                Switch(
                    checked = seat.present,
                    onCheckedChange = { onToggle(seat, it) },
                    modifier = Modifier.testTag(TAG_ATTENDANCE_TOGGLE),
                )
            }
        }
    }

    // **`writable` is the server's decision** [BR1.6, BR5.5]. A
    // cancelled session and an inactive batch both refuse, and testing
    // only the first here would offer a write the server refuses.
    if (state.writable) {
        Button(onClick = onSubmit, modifier = Modifier.testTag(TAG_ATTENDANCE_SUBMIT)) {
            Text(stringResource(R.string.attendance_submit))
        }
    } else {
        Text(
            stringResource(R.string.attendance_read_only),
            Modifier.testTag(TAG_ATTENDANCE_READ_ONLY),
            color = MaterialTheme.colorScheme.error,
        )
    }
}
