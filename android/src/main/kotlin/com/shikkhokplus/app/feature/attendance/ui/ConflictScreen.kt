package com.shikkhokplus.app.feature.attendance.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import com.shikkhokplus.app.feature.attendance.AttendanceSeat
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/** Stable test identifiers. Not user-visible text. */
const val TAG_CONFLICT_TITLE: String = "conflict_title"

/** The explanation of what happened. */
const val TAG_CONFLICT_EXPLANATION: String = "conflict_explanation"

/** The column heading over the teacher's own entry. */
const val TAG_CONFLICT_MINE_HEADING: String = "conflict_mine_heading"

/** The column heading over what the record now says. */
const val TAG_CONFLICT_THEIRS_HEADING: String = "conflict_theirs_heading"

/** The teacher's own roster, preserved. */
const val TAG_CONFLICT_MINE: String = "conflict_mine"

/** The roster the server now holds. */
const val TAG_CONFLICT_THEIRS: String = "conflict_theirs"

/** One comparison row. */
const val TAG_CONFLICT_ROW: String = "conflict_row"

/** The re-apply action. */
const val TAG_CONFLICT_REAPPLY: String = "conflict_reapply"

/** The discard action. */
const val TAG_CONFLICT_DISCARD: String = "conflict_discard"

/**
 * The conflict-resolution screen [BR3.6, FR11.5].
 *
 * **Two rosters side by side, and no third one.** Nothing is merged:
 * merging would mean inventing a rule for a student the two rosters
 * disagree about, which is a business decision no sync layer is
 * authorized to make [ADR-006]. The teacher sees what they recorded
 * offline against what the record now says, and chooses.
 *
 * **Two choices, and neither is a retry.** `Re-apply` composes a NEW
 * write with the current version and a fresh `client_mutation_id`
 * [BR3.7]; `discard` drops the offline entry and keeps what the server
 * holds. A retry control would invite repeating a request that cannot
 * succeed — the version it carries is stale by definition — and worse,
 * it is the control that acquires a version-stripping wrapper, which
 * would overwrite the correction somebody else made.
 *
 * **The offline entry is preserved until the teacher chooses.** It
 * lives in the device queue, not in this composable's state, so
 * backgrounding the app or killing the process does not lose it
 * [BR3.2].
 *
 * **This is the densest Bangla text this unit ships** [BR7.5]. Two
 * labelled columns of names beside two column headings and an
 * explanation, on a phone: the strings are long, they wrap, and the
 * Bangla vowel signs extend above and below the Latin line box. The
 * whole screen scrolls vertically and each row is a `Row` of two
 * weighted halves rather than a fixed-width table, so a name that wraps
 * to three lines pushes its own row rather than clipping. It is the row
 * in `docs/delivery/bangla-layout-check.md` to check hardest.
 *
 * @param state The conflict to resolve
 * @param onReapply Called with the item the teacher chose to re-apply
 * @param onDiscard Called with the item the teacher chose to discard
 * @param modifier Layout modifier
 */
@Composable
fun ConflictScreen(
    state: AttendanceUiState.Conflicted,
    onReapply: (String) -> Unit,
    onDiscard: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier =
            modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            stringResource(
                R.string.conflict_title,
                Numerals.freeText(state.dateLabel),
            ),
            Modifier.testTag(TAG_CONFLICT_TITLE),
            style = MaterialTheme.typography.titleMedium,
        )

        // The server's own message_key, resolved to a local string.
        // Never English text from the server, which the client could
        // not localize [TC-15, D-43].
        Text(
            stringResource(MessageKeys.resolve(state.messageKey)),
            Modifier.testTag(TAG_CONFLICT_EXPLANATION),
        )

        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                stringResource(R.string.conflict_mine_heading),
                Modifier.weight(1f).testTag(TAG_CONFLICT_MINE_HEADING),
                style = MaterialTheme.typography.labelLarge,
            )
            Text(
                stringResource(R.string.conflict_theirs_heading),
                Modifier.weight(1f).testTag(TAG_CONFLICT_THEIRS_HEADING),
                style = MaterialTheme.typography.labelLarge,
            )
        }

        ComparisonRows(state.mine, state.theirs)

        // **Re-apply composes a NEW write** [BR3.7]: the current
        // version, and a freshly generated client_mutation_id. The
        // ViewModel does the composing; what matters here is that this
        // button is not a retry and is not labelled as one.
        Button(
            onClick = { onReapply(state.itemId) },
            modifier = Modifier.fillMaxWidth().testTag(TAG_CONFLICT_REAPPLY),
        ) {
            Text(stringResource(R.string.conflict_reapply))
        }

        TextButton(
            onClick = { onDiscard(state.itemId) },
            modifier = Modifier.fillMaxWidth().testTag(TAG_CONFLICT_DISCARD),
        ) {
            Text(stringResource(R.string.conflict_discard))
        }
    }
}

/**
 * The two rosters, one row per seat.
 *
 * Rows are keyed by the **union** of both rosters rather than by either
 * one, so a seat present in only one side still appears. Showing only
 * the intersection would hide exactly the disagreement the teacher
 * opened this screen to resolve.
 *
 * @param mine What the teacher recorded offline
 * @param theirs What the record now says
 */
@Composable
private fun ComparisonRows(
    mine: List<AttendanceSeat>,
    theirs: List<AttendanceSeat>,
) {
    val byMine = mine.associateBy { it.enrollmentId }
    val byTheirs = theirs.associateBy { it.enrollmentId }
    val seatIds = (mine.map { it.enrollmentId } + theirs.map { it.enrollmentId }).distinct()

    Column(
        Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        for (seatId in seatIds) {
            val own = byMine[seatId]
            val server = byTheirs[seatId]

            Row(
                Modifier.fillMaxWidth().testTag(TAG_CONFLICT_ROW),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                // Two weighted halves rather than a fixed-width table:
                // a long Bangla name wraps inside its own half and
                // pushes the row, instead of being clipped.
                SeatCell(own, Modifier.weight(1f).testTag(TAG_CONFLICT_MINE))
                SeatCell(server, Modifier.weight(1f).testTag(TAG_CONFLICT_THEIRS))
            }
        }
    }
}

/**
 * One side of one comparison row.
 *
 * A seat absent from this side renders an explicit placeholder rather
 * than a blank, so "not on this roster" is readable as itself.
 *
 * @param seat The seat, or null when this side does not hold it
 * @param modifier Layout modifier carrying the weight and tag
 */
@Composable
private fun SeatCell(seat: AttendanceSeat?, modifier: Modifier) {
    Column(modifier) {
        if (seat == null) {
            Text(stringResource(R.string.conflict_seat_absent))
            return@Column
        }

        Text(Numerals.freeText(seat.displayName))
        Text(
            stringResource(
                if (seat.present) {
                    R.string.attendance_present
                } else {
                    R.string.attendance_absent
                },
            ),
        )
    }
}
