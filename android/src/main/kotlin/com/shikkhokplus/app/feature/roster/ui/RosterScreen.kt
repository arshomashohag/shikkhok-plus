package com.shikkhokplus.app.feature.roster.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.model.LinkState
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.roster.RosterRow
import com.shikkhokplus.app.feature.roster.RosterUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_ROSTER_LOADING: String = "roster_loading"

/** The batch name heading. */
const val TAG_ROSTER_TITLE: String = "roster_title"

/** The explanation shown when a batch holds no seats. */
const val TAG_ROSTER_EMPTY: String = "roster_empty"

/** The staleness notice shown when rendering cached data. */
const val TAG_ROSTER_FETCHED_AT: String = "roster_fetched_at"

/** The list of seats. */
const val TAG_ROSTER_LIST: String = "roster_list"

/** One seat. */
const val TAG_ROSTER_ROW: String = "roster_row"

/** The error message. */
const val TAG_ROSTER_ERROR: String = "roster_error"

/** The retry button, shown only when the server said retryable. */
const val TAG_ROSTER_RETRY: String = "roster_retry"

/** The add-student button. */
const val TAG_ROSTER_ADD: String = "roster_add"

/** The attendance entry point. */
const val TAG_ROSTER_SESSIONS: String = "roster_sessions"

/** The marks entry point. */
const val TAG_ROSTER_EXAMS: String = "roster_exams"

/** The accepted-of-total count for this batch. */
const val TAG_ROSTER_ACCEPTED_COUNT: String = "roster_accepted_count"

/** The per-row declined mark. Present on declined rows only. */
const val TAG_ROSTER_DECLINED_MARK: String = "roster_declined_mark"

/** The student link's state on one row. */
const val TAG_ROSTER_STUDENT_STATE: String = "roster_student_state"

/** The guardian link's state on one row. */
const val TAG_ROSTER_GUARDIAN_STATE: String = "roster_guardian_state"

/** The remove action, offered only where the server permits it. */
const val TAG_ROSTER_REMOVE: String = "roster_remove"

/** The removal confirmation. */
const val TAG_ROSTER_REMOVE_CONFIRM: String = "roster_remove_confirm"

/** The refusal shown when removal was not permitted. */
const val TAG_ROSTER_REMOVE_REFUSED: String = "roster_remove_refused"

/** The remedy offered with a refusal. */
const val TAG_ROSTER_REMEDY: String = "roster_remedy"

/** The mark-inactive action, offered for a CLAIMED refusal only. */
const val TAG_ROSTER_MARK_INACTIVE: String = "roster_mark_inactive"

/**
 * The teacher's roster for one batch.
 *
 * **This composable renders a [RosterUiState] and nothing else.** There
 * is no conditional here depending on a domain value — no comparison of
 * a date against today, no threshold on an amount, no decision about
 * what counts as due, and **no comparison of a link state to decide a
 * control**. Every such decision was made by `RosterStateMapper`
 * [TC-9, D-31].
 *
 * That last one is the pressure D2 puts on this file specifically. The
 * row carries `isDeclined`, `isRemovable` and `displayLabel` as fields
 * precisely so that `if (row.studentState == DECLINED)` never appears
 * here — the slip D1 made on `InvitationCard` and corrected, which this
 * unit would otherwise repeat four times over.
 *
 * The link states ARE rendered, and rendering an enum is not comparing
 * one: each maps to its own string resource through an exhaustive
 * `when`, so a fifth state fails to compile rather than rendering as
 * whichever branch was the fallback.
 *
 * Test tags are stable identifiers for the Compose UI test; they are
 * not user-visible text.
 */
@Composable
fun RosterScreen(
    state: RosterUiState,
    onRetry: () -> Unit,
    onAddStudent: () -> Unit = {},
    onOpenSessions: () -> Unit = {},
    onOpenExams: () -> Unit = {},
    onRemove: (RosterRow) -> Unit = {},
    onConfirmRemoval: (RosterRow) -> Unit = {},
    onCancelRemoval: () -> Unit = {},
    onMarkInactive: (RosterRow) -> Unit = {},
    onDismissRefusal: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    // **The class name goes in the bar, not in the body.** It was
    // rendered as default-size body text above the list, which is a
    // title doing a title's job without looking like one. The bar
    // carries it on every state, including the ones that have no
    // name to show yet.
    ListScreenScaffold(
        title =
            when (state) {
                is RosterUiState.Loaded -> state.batchName
                is RosterUiState.Empty -> state.batchName
                else -> stringResource(R.string.roster_title_fallback)
            },
        modifier = modifier,
    ) {
        when (state) {
            RosterUiState.Idle -> Unit

            RosterUiState.Loading ->
                LogoLoader(Modifier.testTag(TAG_ROSTER_LOADING))

            is RosterUiState.Empty -> {
                Button(
                    onClick = onAddStudent,
                    modifier = Modifier.testTag(TAG_ROSTER_ADD),
                ) {
                    Text(stringResource(R.string.student_add_title))
                }
                // An empty list and "no students yet" are different
                // states, and a blank list explains neither.
                Text(
                    stringResource(R.string.roster_empty),
                    Modifier.testTag(TAG_ROSTER_EMPTY),
                )
            }

            is RosterUiState.Loaded ->
                RosterList(state, onAddStudent, onOpenSessions, onOpenExams, onRemove)

            // Both removal states are drawn by `RemoveSeatConfirm.kt`,
            // so the confirmation and its two refusals are one
            // component rather than three branches of this `when`.
            is RosterUiState.ConfirmingRemoval ->
                RemoveSeatConfirm(
                    row = state.row,
                    onConfirm = onConfirmRemoval,
                    onCancel = onCancelRemoval,
                )

            is RosterUiState.RemovalRefused ->
                RemoveSeatRefused(
                    row = state.row,
                    remedy = state.remedy,
                    onMarkInactive = onMarkInactive,
                    onDismiss = onDismissRefusal,
                )

            is RosterUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_ROSTER_ERROR),
                )
                if (state.retryable) {
                    Button(onClick = onRetry, modifier = Modifier.testTag(TAG_ROSTER_RETRY)) {
                        Text(stringResource(R.string.roster_retry))
                    }
                }
            }
        }
    }
}

/**
 * The loaded roster: its count, and one row per seat.
 *
 * @param state The loaded state
 * @param onAddStudent Called when the teacher wants a new seat
 * @param onRemove Called with the row the teacher wants removed
 */
@Composable
private fun RosterList(
    state: RosterUiState.Loaded,
    onAddStudent: () -> Unit,
    onOpenSessions: () -> Unit,
    onOpenExams: () -> Unit,
    onRemove: (RosterRow) -> Unit,
) {
    // **"9 of 12 accepted"** [AC1.3.5a]. The count is at BATCH level
    // because pending is the normal state of a new seat and marking
    // every pending row would flag normality as a problem [BR1.1].
    state.accepted?.let { counts ->
        Text(
            stringResource(
                R.string.roster_accepted_count,
                Numerals.count(counts.accepted),
                Numerals.count(counts.total),
            ),
            Modifier.testTag(TAG_ROSTER_ACCEPTED_COUNT),
        )
    }
    Button(onClick = onAddStudent, modifier = Modifier.testTag(TAG_ROSTER_ADD)) {
        Text(stringResource(R.string.student_add_title))
    }

    // **The roster is where a class's work starts.** Attendance and
    // marks were both built and neither could be opened: the sessions
    // list and the exam list had routes and nothing navigated to them.
    // This is the same gap the navigation graph exists to close, one
    // level further in.
    Button(
        onClick = onOpenSessions,
        modifier = Modifier.testTag(TAG_ROSTER_SESSIONS),
    ) {
        Text(stringResource(R.string.roster_open_sessions))
    }
    Button(onClick = onOpenExams, modifier = Modifier.testTag(TAG_ROSTER_EXAMS)) {
        Text(stringResource(R.string.roster_open_exams))
    }
    state.fetchedAtLabel?.let { label ->
        // The cache is a READ cache, and saying so is part of the
        // contract: a teacher must know when they are looking at saved
        // data rather than live data.
        Text(
            stringResource(R.string.roster_fetched_at, label),
            Modifier.testTag(TAG_ROSTER_FETCHED_AT),
        )
    }
    LazyColumn(Modifier.testTag(TAG_ROSTER_LIST)) {
        items(state.rows, key = { it.enrollmentId }) { row ->
            RosterRowView(row, onRemove)
        }
    }
}

/**
 * One seat.
 *
 * The status label is a **resource key the mapper chose** from the
 * server's enum. This composable looks up a string and renders it; it
 * does not decide which one.
 *
 * **Both link states appear and the seat appears once** [BR2.1,
 * AC1.10.7]. A student who accepted beside a guardian who declined is a
 * real seat and neither single value describes it.
 *
 * @param row The row to render
 * @param onRemove Called when the teacher asks to remove this seat
 */
@Composable
private fun RosterRowView(row: RosterRow, onRemove: (RosterRow) -> Unit) {
    Column(Modifier.fillMaxWidth().testTag(TAG_ROSTER_ROW)) {
        // **`displayLabel`, not `displayName`** [BR2.3, NFR14.28]. The
        // mapper chose the number for a declined seat and the name
        // otherwise; this renders whichever it was handed and never
        // reaches for the name itself.
        //
        // Null means a declined seat with no number recorded. The
        // placeholder is shown rather than the name, because BR2.3
        // forbids displaying a name for someone who has declined and
        // does not make an exception for having nothing else to show.
        Text(
            row.displayLabel?.let { Numerals.freeText(it) }
                ?: stringResource(R.string.roster_declined_no_number),
        )
        Text(stringResource(MessageKeys.resolve(row.statusLabel)))

        Text(
            stringResource(
                R.string.guardian_child_in_batch,
                stringResource(R.string.roster_link_student),
                stringResource(linkStateLabel(row.studentState)),
            ),
            Modifier.testTag(TAG_ROSTER_STUDENT_STATE),
        )
        Text(
            stringResource(
                R.string.guardian_child_in_batch,
                stringResource(R.string.roster_link_guardian),
                stringResource(linkStateLabel(row.guardianState)),
            ),
            Modifier.testTag(TAG_ROSTER_GUARDIAN_STATE),
        )

        // **`isDeclined`, decided by the mapper** [BR1.1]. Declined is
        // marked because it is abnormal and usually a mistyped number;
        // pending is NOT marked, because it is normal.
        if (row.isDeclined) {
            Text(
                stringResource(R.string.roster_declined_mark),
                Modifier.testTag(TAG_ROSTER_DECLINED_MARK),
                color = MaterialTheme.colorScheme.error,
            )
        }

        // **`isRemovable` is the SERVER's decision** [BR3.1]. Not
        // derived from the two states above: removal also reads the
        // erasure markers, which this row does not carry.
        if (row.isRemovable) {
            TextButton(
                onClick = { onRemove(row) },
                modifier = Modifier.testTag(TAG_ROSTER_REMOVE),
            ) {
                Text(stringResource(R.string.roster_remove))
            }
        }
    }
}

/**
 * The string resource naming one link's state.
 *
 * **Exhaustive over [LinkState]**, so a fifth value fails to compile
 * rather than rendering under whichever branch happened to be the
 * fallback — the same rule the mapper applies to the wire tokens.
 *
 * Rendering an enum is not comparing one: this maps a value the server
 * decided onto the words for it, and chooses no behaviour.
 *
 * @param state The link's state
 * @return The string resource id
 */
private fun linkStateLabel(state: LinkState): Int = when (state) {
    LinkState.PENDING -> R.string.roster_link_pending
    LinkState.ACCEPTED -> R.string.roster_link_accepted
    LinkState.DECLINED -> R.string.roster_link_declined
    LinkState.ABSENT -> R.string.roster_link_absent
}
