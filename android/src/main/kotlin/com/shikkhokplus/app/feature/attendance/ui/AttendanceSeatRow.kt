package com.shikkhokplus.app.feature.attendance.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.attendance.AttendanceSeat

/**
 * One seat on the roster: the student's name and a present/absent switch.
 *
 * **The whole row is the switch** [UX-2]. A bare `Switch` beside a separate
 * `Text` gave TalkBack "On, switch" with no name. The row carries
 * `toggleable(role = Role.Switch)`, so its semantics merge the name, and the
 * `Switch` takes `onCheckedChange = null` and only draws the state -- the
 * pattern `BatchFeeToggle` and the settings screen already use. The state is
 * read out as "Present" or "Absent" rather than "On" or "Off". Tapping
 * anywhere on the row toggles, which also widens the target to the row.
 *
 * [TAG_ATTENDANCE_SEAT] marks the seat; [TAG_ATTENDANCE_TOGGLE] marks the
 * toggleable node, the one that holds the name, state and enabled flag.
 *
 * @param seat The seat
 * @param enabled Whether the mark may change; false when the server refuses
 * @param showWord Whether to draw the state word beside the switch
 * @param onToggle Called with the seat and its new mark
 */
@Composable
internal fun AttendanceSeatRow(
    seat: AttendanceSeat,
    enabled: Boolean,
    showWord: Boolean,
    onToggle: (AttendanceSeat, Boolean) -> Unit,
) {
    val word = stringResource(if (seat.present) R.string.attendance_present else R.string.attendance_absent)
    Box(Modifier.fillMaxWidth().testTag(TAG_ATTENDANCE_SEAT)) {
        Row(
            Modifier
                .fillMaxWidth()
                .heightIn(min = 48.dp)
                .toggleable(
                    value = seat.present,
                    enabled = enabled,
                    role = Role.Switch,
                    onValueChange = { onToggle(seat, it) },
                )
                .semantics { stateDescription = word }
                .padding(vertical = 2.dp)
                .testTag(TAG_ATTENDANCE_TOGGLE),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(Numerals.freeText(seat.displayName), Modifier.weight(1f))
            if (showWord) {
                // Already read out as the state description; not twice.
                Text(
                    word,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(end = 8.dp).clearAndSetSemantics {},
                )
            }
            Switch(checked = seat.present, onCheckedChange = null, enabled = enabled)
        }
    }
}
