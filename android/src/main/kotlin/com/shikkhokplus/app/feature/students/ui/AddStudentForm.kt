package com.shikkhokplus.app.feature.students.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.network.StudentSeatBody
import com.shikkhokplus.app.core.ui.PhoneNumberField
import com.shikkhokplus.app.core.ui.TAG_FORM_CANCEL
import com.shikkhokplus.app.core.ui.TAG_FORM_ERROR
import com.shikkhokplus.app.core.ui.TAG_FORM_GUARDIAN
import com.shikkhokplus.app.core.ui.TAG_FORM_NAME
import com.shikkhokplus.app.core.ui.TAG_FORM_STUDENT_PHONE
import com.shikkhokplus.app.core.ui.TAG_FORM_SUBMIT
import com.shikkhokplus.app.core.ui.canonicalFee
import com.shikkhokplus.app.core.ui.feeIsValid
import com.shikkhokplus.app.core.ui.phoneError
import com.shikkhokplus.app.core.ui.phoneIsValid
import com.shikkhokplus.app.feature.students.BatchOption

/** The batch multi-select. Not user-visible text. */
const val TAG_FORM_BATCHES: String = "form_batches"

/** One choice in the batch multi-select. */
const val TAG_FORM_BATCH_OPTION: String = "form_batch_option"

/** One chosen batch's own fee field. */
const val TAG_FORM_SEAT_FEE: String = "form_seat_fee"

/**
 * What the add-student form sends.
 *
 * @property name The typed name
 * @property studentPhone The typed student number, or null
 * @property guardianPhone The typed guardian number, or null
 * @property seats The chosen batches, each with its own fee or null
 */
data class NewStudent(
    val name: String,
    val studentPhone: String?,
    val guardianPhone: String?,
    val seats: List<StudentSeatBody>,
)

/**
 * Add a student to the teacher's list, and suggest batches [D3].
 *
 * **Batches are suggested, never required**: the multi-select may be
 * left empty and the student is saved with no batch. Each chosen batch
 * charges its own fee unless a different one is typed beside it; blank
 * means INHERIT, never zero, because zero is a waiver [AC2.2.5].
 *
 * Client checks are FORMAT only. A number already on the teacher's list
 * is refused by the server and shown here beside what was typed [D2].
 *
 * @param batches The teacher's batches, to choose from
 * @param onSave Called with what to send
 * @param onCancel Called when the teacher backs out
 * @param modifier The layout modifier
 * @param saving True while the write is in flight
 * @param error Why the last write failed, already resolved, or null
 * @param preselected A batch to start chosen, when opened from a roster
 * @param existingNames The teacher's students, for the same-name hint
 */
@Composable
fun AddStudentForm(
    batches: List<BatchOption>,
    onSave: (NewStudent) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
    saving: Boolean = false,
    error: String? = null,
    preselected: String? = null,
    existingNames: List<String> = emptyList(),
) {
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var guardian by remember { mutableStateOf("") }
    // Batch id to the fee typed for it; blank inherits the batch's fee.
    val chosen = remember { mutableStateMapOf<String, String>().apply { preselected?.let { put(it, "") } } }

    val phoneOk = phone.isBlank() || phoneIsValid(phone)
    val guardianOk = guardian.isBlank() || phoneIsValid(guardian)
    val feesOk = chosen.values.all(::feeIsValid)
    val ready = !saving && name.isNotBlank() && phoneOk && guardianOk && feesOk

    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            label = { Text(stringResource(R.string.student_add_name)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_NAME),
        )
        SameNameHint(name, existingNames)
        PhoneNumberField(
            value = phone,
            onValueChange = { phone = it },
            label = stringResource(R.string.student_add_student_phone),
            help = stringResource(R.string.student_add_student_phone_help),
            error = phoneError(phone),
            fieldModifier = Modifier.testTag(TAG_FORM_STUDENT_PHONE),
            modifier = Modifier.fillMaxWidth(),
        )
        PhoneNumberField(
            value = guardian,
            onValueChange = { guardian = it },
            label = stringResource(R.string.student_add_guardian),
            error = phoneError(guardian),
            fieldModifier = Modifier.testTag(TAG_FORM_GUARDIAN),
            modifier = Modifier.fillMaxWidth(),
        )
        BatchMultiSelect(
            batches = batches,
            chosen = chosen.keys,
            onToggle = { id -> if (id in chosen) chosen.remove(id) else chosen[id] = "" },
        )
        batches.filter { it.id in chosen }.forEach { batch ->
            SeatFeeField(batch, chosen[batch.id].orEmpty()) { chosen[batch.id] = it }
        }
        if (chosen.isEmpty()) {
            Text(
                text = stringResource(R.string.student_add_no_batch),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        error?.let {
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.testTag(TAG_FORM_ERROR),
            )
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    onSave(
                        NewStudent(
                            name = name.trim(),
                            studentPhone = phone.trim().ifBlank { null },
                            guardianPhone = guardian.trim().ifBlank { null },
                            seats =
                                batches
                                    .filter { it.id in chosen }
                                    .map { StudentSeatBody(it.id, canonicalFee(chosen[it.id].orEmpty())) },
                        ),
                    )
                },
                enabled = ready,
                modifier = Modifier.testTag(TAG_FORM_SUBMIT),
            ) {
                Text(stringResource(R.string.student_add_submit))
            }
            TextButton(onClick = onCancel, modifier = Modifier.testTag(TAG_FORM_CANCEL)) {
                Text(stringResource(R.string.action_cancel))
            }
        }
    }
}

/**
 * "Add to batches (optional)": a field that opens a checklist of batches.
 *
 * @param batches The teacher's batches
 * @param chosen The ids chosen so far
 * @param onToggle Called with a batch id to choose or unchoose it
 */
@Composable
internal fun BatchMultiSelect(batches: List<BatchOption>, chosen: Set<String>, onToggle: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = stringResource(R.string.student_add_batches),
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (batches.isEmpty()) {
            Text(
                text = stringResource(R.string.student_add_batches_none),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            return@Column
        }
        Box {
            OutlinedButton(
                onClick = { open = true },
                modifier = Modifier.fillMaxWidth().heightIn(min = Reach.touch).testTag(TAG_FORM_BATCHES),
                shape = MaterialTheme.shapes.small,
            ) {
                val names = batches.filter { it.id in chosen }.joinToString(", ") { Numerals.freeText(it.name) }
                Text(
                    text = names.ifEmpty { stringResource(R.string.student_add_batches_choose) },
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                batches.forEach { batch ->
                    DropdownMenuItem(
                        text = { Text(Numerals.freeText(batch.name)) },
                        leadingIcon = { Checkbox(checked = batch.id in chosen, onCheckedChange = null) },
                        trailingIcon = { batch.defaultFee?.let { Text(Numerals.money(it)) } },
                        onClick = { onToggle(batch.id) },
                        modifier = Modifier.testTag(TAG_FORM_BATCH_OPTION),
                    )
                }
            }
        }
        Text(
            text = stringResource(R.string.student_add_batches_help),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * One chosen batch's fee: its own by default, or a different one typed.
 *
 * @param batch The chosen batch
 * @param fee What was typed; blank inherits the batch's fee
 * @param onChange Called with the new text
 */
@Composable
private fun SeatFeeField(batch: BatchOption, fee: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = fee,
        onValueChange = onChange,
        label = { Text(stringResource(R.string.student_add_seat_fee, Numerals.freeText(batch.name))) },
        placeholder = {
            batch.defaultFee?.let { Text(stringResource(R.string.student_add_batch_fee, Numerals.money(it))) }
        },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        isError = !feeIsValid(fee),
        supportingText = {
            Text(stringResource(if (feeIsValid(fee)) R.string.fee_inherits else R.string.fee_invalid))
        },
        modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_SEAT_FEE),
    )
}

/**
 * "Rahim is already on your list", when the typed name matches one. A
 * hint, never a block: two students can share a name [D2].
 *
 * @param name What was typed
 * @param existingNames The teacher's students
 */
@Composable
private fun SameNameHint(name: String, existingNames: List<String>) {
    if (name.isBlank()) return
    val match = existingNames.firstOrNull { it.trim().equals(name.trim(), ignoreCase = true) } ?: return
    Text(
        stringResource(R.string.student_add_same_name_any, match),
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}
