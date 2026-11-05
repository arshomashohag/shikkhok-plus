package com.shikkhokplus.app.feature.students.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonBlock
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.PhoneNumberField
import com.shikkhokplus.app.core.ui.phoneError
import com.shikkhokplus.app.core.ui.phoneIsValid
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.students.SeatLine
import com.shikkhokplus.app.feature.students.StudentDetail
import com.shikkhokplus.app.feature.students.StudentDetailUiState

/** One seat on the student. Not user-visible text. */
const val TAG_STUDENT_SEAT: String = "student_seat"

/** "Add to another batch". */
const val TAG_STUDENT_ADD_BATCH: String = "student_add_batch"

/** "Remove student". */
const val TAG_STUDENT_REMOVE: String = "student_remove"

/** The refusal of the last action. */
const val TAG_STUDENT_ACTION_ERROR: String = "student_action_error"

/**
 * What the student screen can be asked to do.
 *
 * @property onBack Called to leave
 * @property onRetry Called when the teacher asks to retry the read
 * @property onOpenSeat Called with a seat id, to open its fee history
 * @property onEnroll Called with a batch id, to add the student to it
 * @property onLeave Called with a seat id: the student left that batch
 * @property onRemoveSeat Called with a seat id nobody accepted
 * @property onEdit Called with a new name, student number and guardian
 *   number, each null to keep it
 * @property onRemove Called to remove the student
 */
data class StudentDetailActions(
    val onBack: () -> Unit,
    val onRetry: () -> Unit,
    val onOpenSeat: (SeatLine) -> Unit,
    val onEnroll: (String) -> Unit,
    val onLeave: (String) -> Unit,
    val onRemoveSeat: (String) -> Unit,
    val onEdit: (String?, String?, String?) -> Unit,
    val onRemove: () -> Unit,
)

/**
 * One student: invitations, what they owe, their batches, and actions.
 *
 * Fees, attendance and marks stay per batch [D5]; tapping a batch opens
 * that seat's fee history. Every figure and every "may" is the server's.
 *
 * @param state What to render
 * @param actionError Why the last action was refused, resolved, or null
 * @param actions What the screen can be asked to do
 * @param modifier The layout modifier
 */
@Composable
fun StudentDetailScreen(
    state: StudentDetailUiState,
    actionError: String?,
    actions: StudentDetailActions,
    modifier: Modifier = Modifier,
) {
    val loaded = (state as? StudentDetailUiState.Loaded)?.student
    ScreenScaffold(
        title = loaded?.let { Numerals.freeText(it.name) } ?: stringResource(R.string.students_title),
        subtitle = loaded?.studentPhone,
        onBack = actions.onBack,
        modifier = modifier,
    ) {
        when (state) {
            StudentDetailUiState.Loading, StudentDetailUiState.Removed ->
                ShikkhokCard {
                    SkeletonBlock(widthFraction = 0.6f, height = 16.dp)
                    SkeletonBlock(widthFraction = 0.4f, height = 12.dp)
                }

            is StudentDetailUiState.Failed ->
                EmptyState(
                    title = stringResource(R.string.student_detail_error_title),
                    body = stringResource(MessageKeys.resolve(state.messageKey)),
                ) {
                    if (state.retryable) {
                        OutlinedButton(onClick = actions.onRetry) { Text(stringResource(R.string.roster_retry)) }
                    }
                }

            is StudentDetailUiState.Loaded -> StudentBody(state.student, actionError, actions)
        }
    }
}

/**
 * The loaded student.
 *
 * @param student The student
 * @param actionError Why the last action was refused, or null
 * @param actions What the screen can be asked to do
 */
@Composable
private fun StudentBody(student: StudentDetail, actionError: String?, actions: StudentDetailActions) {
    var leaving by remember { mutableStateOf<SeatLine?>(null) }
    var removing by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf(false) }

    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        LinksCard(student)
        actionError?.let {
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.testTag(TAG_STUDENT_ACTION_ERROR),
            )
        }
        SectionLabel(stringResource(R.string.student_detail_batches))
        if (student.seats.isEmpty()) {
            Text(
                text = stringResource(R.string.student_detail_no_batches),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        student.seats.forEach { seat ->
            SeatCard(
                seat = seat,
                onOpen = { actions.onOpenSeat(seat) },
                onLeave = { leaving = seat },
                onRemove = { actions.onRemoveSeat(seat.enrollmentId) },
            )
        }
        AddToBatch(student, actions.onEnroll)
        OutlinedButton(
            onClick = { editing = true },
            modifier = Modifier.fillMaxWidth().heightIn(min = Reach.touch),
        ) {
            Text(stringResource(R.string.student_detail_edit))
        }
        RemoveStudent(student.removable) { removing = true }
    }

    leaving?.let { seat ->
        ConfirmDialog(
            title = stringResource(R.string.student_detail_leave_title, student.name, seat.batchName),
            body = stringResource(R.string.student_detail_leave_body),
            onConfirm = {
                leaving = null
                actions.onLeave(seat.enrollmentId)
            },
            onDismiss = { leaving = null },
        )
    }
    if (removing) {
        ConfirmDialog(
            title = stringResource(R.string.student_detail_remove_title, student.name),
            body = stringResource(R.string.student_detail_remove_body),
            onConfirm = {
                removing = false
                actions.onRemove()
            },
            onDismiss = { removing = false },
        )
    }
    if (editing) {
        EditStudentDialog(
            student = student,
            onSave = { name, phone, guardian ->
                editing = false
                actions.onEdit(name, phone, guardian)
            },
            onDismiss = { editing = false },
        )
    }
}

/**
 * Who has accepted, and what is owed in total.
 *
 * @param student The student
 */
@Composable
private fun LinksCard(student: StudentDetail) {
    ShikkhokCard {
        LabelValue(stringResource(R.string.student_detail_student_link), linkLabel(student.studentState))
        LabelValue(
            label =
                student.guardianPhone?.let { stringResource(R.string.student_detail_guardian_link) + " · " + it }
                    ?: stringResource(R.string.student_detail_guardian_link),
            value =
                if (student.guardianState == ABSENT) {
                    stringResource(R.string.student_detail_no_guardian)
                } else {
                    linkLabel(student.guardianState)
                },
        )
        LabelValue(stringResource(R.string.student_detail_total_due), Numerals.money(student.totalOutstanding))
    }
}

/** The server's value for "no guardian recorded". */
private const val ABSENT = "absent"

/**
 * The words for one link's state, as the server named it.
 *
 * @param state `pending`, `accepted` or `declined`
 * @return The label
 */
@Composable
private fun linkLabel(state: String): String =
    stringResource(
        when (state) {
            "accepted" -> R.string.student_link_accepted
            "declined" -> R.string.student_link_declined
            else -> R.string.student_link_pending
        },
    )

/**
 * One seat, with its fee, what it owes, and its actions.
 *
 * @param seat The seat
 * @param onOpen Called to open the seat's fee history
 * @param onLeave Called when the student leaves this batch
 * @param onRemove Called to delete the seat
 */
@Composable
private fun SeatCard(seat: SeatLine, onOpen: () -> Unit, onLeave: () -> Unit, onRemove: () -> Unit) {
    ShikkhokCard(modifier = Modifier.testTag(TAG_STUDENT_SEAT), onClick = onOpen) {
        Text(
            text = Numerals.freeText(seat.batchName),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
        )
        val fee = seat.fee?.let { stringResource(R.string.student_detail_seat_fee, Numerals.money(it)) }
        val due = stringResource(R.string.student_detail_seat_due, Numerals.money(seat.outstanding))
        Text(
            text = listOfNotNull(fee, due).joinToString(" · "),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            if (!seat.active) {
                Text(
                    text = stringResource(R.string.student_detail_left),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            // The server says which removal applies: a seat nobody
            // accepted is deleted; any other seat is left, keeping its
            // history and its dues [D4].
            if (seat.removable) {
                TextButton(onClick = onRemove) { Text(stringResource(R.string.student_detail_remove_seat)) }
            } else if (seat.active) {
                TextButton(onClick = onLeave) { Text(stringResource(R.string.student_detail_leave)) }
            }
        }
    }
}

/**
 * "Add to another batch": the batches the student is not in yet.
 *
 * @param student The student
 * @param onEnroll Called with the chosen batch id
 */
@Composable
private fun AddToBatch(student: StudentDetail, onEnroll: (String) -> Unit) {
    if (student.otherBatches.isEmpty()) return
    var open by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(
            onClick = { open = true },
            modifier = Modifier.fillMaxWidth().heightIn(min = Reach.touch).testTag(TAG_STUDENT_ADD_BATCH),
        ) {
            Text(stringResource(R.string.student_detail_add_batch))
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            student.otherBatches.forEach { batch ->
                DropdownMenuItem(
                    text = { Text(Numerals.freeText(batch.name)) },
                    trailingIcon = { batch.defaultFee?.let { Text(Numerals.money(it)) } },
                    onClick = {
                        open = false
                        onEnroll(batch.id)
                    },
                )
            }
        }
    }
}

/**
 * "Remove student", or why it is not available yet [D4].
 *
 * @param removable The server's answer
 * @param onRemove Called when tapped
 */
@Composable
private fun RemoveStudent(removable: Boolean, onRemove: () -> Unit) {
    if (removable) {
        TextButton(onClick = onRemove, modifier = Modifier.testTag(TAG_STUDENT_REMOVE)) {
            Text(stringResource(R.string.student_detail_remove), color = MaterialTheme.colorScheme.error)
        }
    } else {
        Text(
            text = stringResource(R.string.student_detail_remove_blocked),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * Edit the name and, while still changeable, the two numbers.
 *
 * A number someone accepted cannot be changed; the server refuses and
 * the refusal is shown on the screen.
 *
 * @param student The student as loaded
 * @param onSave Called with the changed values, each null when unchanged
 * @param onDismiss Called to close without saving
 */
@Composable
private fun EditStudentDialog(
    student: StudentDetail,
    onSave: (String?, String?, String?) -> Unit,
    onDismiss: () -> Unit,
) {
    var name by remember { mutableStateOf(student.name) }
    var phone by remember { mutableStateOf(student.studentPhone.orEmpty()) }
    var guardian by remember { mutableStateOf(student.guardianPhone.orEmpty()) }
    val ready =
        name.isNotBlank() && (phone.isBlank() || phoneIsValid(phone)) && (guardian.isBlank() || phoneIsValid(guardian))
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.student_detail_edit)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text(stringResource(R.string.student_add_name)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                PhoneNumberField(
                    value = phone,
                    onValueChange = { phone = it },
                    label = stringResource(R.string.student_add_student_phone),
                    error = phoneError(phone),
                    modifier = Modifier.fillMaxWidth(),
                )
                PhoneNumberField(
                    value = guardian,
                    onValueChange = { guardian = it },
                    label = stringResource(R.string.student_add_guardian),
                    error = phoneError(guardian),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = ready,
                onClick = {
                    onSave(
                        name.trim().takeIf { it != student.name },
                        phone.trim().takeIf { it.isNotBlank() && it != student.studentPhone },
                        guardian.trim().takeIf { it.isNotBlank() && it != student.guardianPhone },
                    )
                },
            ) {
                Text(stringResource(R.string.student_detail_save))
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) } },
    )
}

/**
 * A yes-or-cancel question before a change that matters.
 *
 * @param title The question
 * @param body What will happen
 * @param onConfirm Called on yes
 * @param onDismiss Called on cancel
 */
@Composable
private fun ConfirmDialog(title: String, body: String, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(body) },
        confirmButton = { TextButton(onClick = onConfirm) { Text(stringResource(R.string.action_confirm)) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) } },
    )
}

/**
 * A section heading.
 *
 * @param text The heading
 */
@Composable
private fun SectionLabel(text: String) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/**
 * One label and its value on a line.
 *
 * @param label The label
 * @param value The value
 */
@Composable
private fun LabelValue(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        Text(text = value, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
    }
}
