package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ScheduleSlotDto

/** Stable test identifiers. Not user-visible text. */
const val TAG_FORM_NAME: String = "form_name"

/** The student's phone field on the add-student form. */
const val TAG_FORM_STUDENT_PHONE: String = "form_student_phone"

/** The due-day field on the class form. */
const val TAG_FORM_DUE_DAY: String = "form_due_day"

/** The write's refusal, shown on the form that caused it. */
const val TAG_FORM_ERROR: String = "form_error"

/** The subjects field on the class form. */
const val TAG_FORM_SUBJECTS: String = "form_subjects"

/** The fee field on either form. */
const val TAG_FORM_FEE: String = "form_fee"

/** The add-student form's "Batch fee" toggle (T8). */
const val TAG_FORM_BATCH_FEE: String = "form_batch_fee"

/** The guardian phone field on the student form. */
const val TAG_FORM_GUARDIAN: String = "form_guardian"

/** The submit button. */
const val TAG_FORM_SUBMIT: String = "form_submit"

/** The same-name hint on the add-student form (T8). */
const val TAG_FORM_SAME_NAME: String = "form_same_name"

/** "Save & add next" on the add-student form (T8). */
const val TAG_FORM_SUBMIT_NEXT: String = "form_submit_next"

/** The cancel button. */
const val TAG_FORM_CANCEL: String = "form_cancel"

/**
 * Split a comma-separated subject field into the list the API takes.
 *
 * Extracted so it can be tested as the pure function it is. Driving two
 * text fields and a button through Robolectric to assert a string split
 * tests Compose's input handling, which is not the thing at risk.
 *
 * @param raw What the teacher typed
 * @return The non-empty, trimmed subjects
 */
fun splitSubjects(raw: String): List<String> =
    raw.split(",").map(String::trim).filter(String::isNotEmpty)

/**
 * What the batch form starts from, when it edits rather than creates.
 *
 * @property name The batch's name
 * @property subjects Its subjects, comma-separated as typed
 * @property fee Its fee as the canonical string, or blank
 * @property dueDay Its due day, or blank
 */
data class BatchFormValues(
    val name: String = "",
    val subjects: String = "",
    val fee: String = "",
    val dueDay: String = "",
)

/**
 * Create a class, or edit one.
 *
 * **Client-side validation is FORMAT only, never policy** [layering
 * rules]. The submit button is disabled until a name exists, which is
 * an optimization so the teacher is not sent on a round trip to learn
 * a field is blank — and the server rejects a blank name too. A client
 * check with no server counterpart would be a business rule living on
 * the client.
 *
 * @param onCreate Called with name, subjects, the fee in canonical form,
 *   the due day, and the weekly classes (possibly none)
 * @param onCancel Called when the teacher backs out
 * @param modifier The layout modifier
 * @param saving True while the write is in flight; the form stays open
 *   and cannot submit twice
 * @param error Why the last write failed, already resolved to text, or
 *   null. The typed values stay in the fields beside it
 * @param initial What the fields start with; blank to create
 * @param withSchedule Whether to offer class days. An edit leaves them
 *   to the batch's own schedule screen
 * @param submitLabel The submit button's words
 */
@Composable
fun BatchCreateForm(
    onCreate: (String, List<String>, String?, Int?, List<ScheduleSlotDto>) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
    saving: Boolean = false,
    error: String? = null,
    initial: BatchFormValues = BatchFormValues(),
    withSchedule: Boolean = true,
    submitLabel: String = stringResource(R.string.batch_create_submit),
) {
    var name by remember { mutableStateOf(initial.name) }
    var subjects by remember { mutableStateOf(initial.subjects) }
    var fee by remember { mutableStateOf(initial.fee) }
    var dueDay by remember { mutableStateOf(initial.dueDay) }
    var schedule by remember { mutableStateOf(ScheduleDraft()) }

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // **No heading and no padding here.** The screen that
        // hosts this form puts its name in the app bar and owns
        // the margin. Rendering a titleLarge here as well is the
        // "parent view holding a child view" doubling reported on
        // a device: the same words twice, once in the bar and once
        // just below it.

        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            label = { Text(stringResource(R.string.batch_create_name)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_NAME),
        )
        OutlinedTextField(
            value = subjects,
            onValueChange = { subjects = it },
            label = { Text(stringResource(R.string.batch_create_subjects)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_SUBJECTS),
        )
        OutlinedTextField(
            value = fee,
            onValueChange = { fee = it },
            label = { Text(stringResource(R.string.batch_create_fee)) },
            singleLine = true,
            // Decimal, because a money value carries two places. The
            // field is still a STRING all the way to the wire [TC-7].
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            isError = !feeIsValid(fee),
            supportingText =
                if (feeIsValid(fee)) {
                    null
                } else {
                    { Text(stringResource(R.string.fee_invalid)) }
                },
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_FEE),
        )
        OutlinedTextField(
            value = dueDay,
            onValueChange = { dueDay = it.filter(Char::isDigit).take(2) },
            label = { Text(stringResource(R.string.batch_create_due_day)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            isError = !dueDayIsValid(dueDay),
            supportingText =
                if (dueDayIsValid(dueDay)) {
                    null
                } else {
                    { Text(stringResource(R.string.due_day_invalid)) }
                },
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_DUE_DAY),
        )
        // **Class days, so the batch has sessions from the start.** A
        // batch created without them had no schedule, so no session was
        // ever generated and attendance could not be taken (T0: "name the
        // batch and pick its class days, time and monthly fee").
        if (withSchedule) ScheduleEditor(draft = schedule, onChange = { schedule = it })

        // **Shown on the form, beside what was typed.** The form used
        // to close before the server answered, so a refusal had nowhere
        // to appear and was overwritten by a list reload.
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
                    onCreate(
                        name.trim(),
                        splitSubjects(subjects),
                        canonicalFee(fee),
                        dueDay.trim().toIntOrNull(),
                        schedule.toSlots(),
                    )
                },
                // **`subjects` too, not just the name.** The server
                // requires `minItems: 1` and `splitSubjects` filters
                // empties, so an untouched subjects field submitted an
                // empty array -- which FastAPI rejects with a raw 422
                // carrying no message_key, so the envelope could render
                // nothing and the screen looked like the button simply
                // did not work. Reported as "I can't create batches".
                //
                // Format only, never policy: this checks a required
                // field is present, which the contract states. It does
                // not duplicate any server decision.
                enabled =
                    !saving &&
                        name.isNotBlank() &&
                        splitSubjects(subjects).isNotEmpty() &&
                        feeIsValid(fee) &&
                        dueDayIsValid(dueDay) &&
                        schedule.isValid,
                modifier = Modifier.testTag(TAG_FORM_SUBMIT),
            ) {
                Text(submitLabel)
            }
            TextButton(onClick = onCancel, modifier = Modifier.testTag(TAG_FORM_CANCEL)) {
                Text(stringResource(R.string.action_cancel))
            }
        }
    }
}

/**
 * The fee to send, read from what was typed.
 *
 * **Canonical form, never the raw text.** Both forms used to send the
 * field as typed, and the server accepts only `1500.00`: a teacher
 * typing `1500` was refused, and the refusal was hidden, so the class
 * or student was silently never created.
 *
 * Blank is `null` -- INHERIT, never zero [AC2.2.5]. Text that is not an
 * amount is also `null` here, but the forms never reach this with such
 * text, because [feeIsValid] keeps the submit button disabled.
 *
 * @param raw The fee field as typed
 * @return The canonical amount, or null to inherit
 */
internal fun canonicalFee(raw: String): String? =
    if (raw.isBlank()) null else Money.fromTyped(raw)?.toString()

/**
 * Whether the fee field holds something submittable.
 *
 * Blank is valid -- it inherits. Anything else must read as an amount.
 * **Format only**, which the contract states; whether the amount is
 * acceptable is the server's decision.
 *
 * @param raw The fee field as typed
 * @return True when blank or a readable amount
 */
internal fun feeIsValid(raw: String): Boolean = raw.isBlank() || Money.fromTyped(raw) != null

/** Bangla digit zero; the nine after it are contiguous. */
private const val BANGLA_ZERO = '\u09E6'

/** A Bangladeshi mobile number once its country code is removed. */
private val LOCAL_MOBILE = Regex("01[3-9][0-9]{8}")

/**
 * Whether a phone field holds a Bangladeshi mobile number.
 *
 * **Format only, mirroring the server's own check**, so a teacher learns
 * about a ten-digit number while typing rather than after a round trip.
 * The server canonicalises and decides; this only spares the wait.
 * Accepts the same spellings: separators, `+880`/`880`/`00880`, and
 * Bangla digits.
 *
 * @param raw The field as typed
 * @return True when it is a mobile number in any accepted spelling
 */
internal fun phoneIsValid(raw: String): Boolean {
    var text =
        raw
            .map { char -> if (char - BANGLA_ZERO in 0..9) '0' + (char - BANGLA_ZERO) else char }
            .filterNot { it.isWhitespace() || it in "-()." }
            .joinToString("")
    text = text.removePrefix("+").let { if (it.startsWith("00")) it.drop(2) else it }
    if (text.startsWith("880")) text = "0" + text.drop(3)
    return LOCAL_MOBILE.matches(text)
}

/** The range a due day may take, as the server states it. */
private val DUE_DAYS: IntRange = 1..31

/**
 * Whether the due-day field holds something submittable.
 *
 * Blank is valid -- no due day. Otherwise 1 to 31, the range the server
 * enforces: `0` and `45` were both accepted by this field and refused
 * there. A format check, like the fee's.
 *
 * @param raw The field as typed
 * @return True when blank or a day of the month
 */
internal fun dueDayIsValid(raw: String): Boolean =
    raw.isBlank() || raw.toIntOrNull()?.let { it in DUE_DAYS } == true

/**
 * What is wrong with a typed number, or null when nothing is.
 *
 * "This one has 10 digits" when the count is off (T8), since a wrong
 * count is the mistake a teacher makes reading a number off a register;
 * otherwise the general message. A blank field is not an error here --
 * the form's required check is the submit button.
 *
 * @param raw The field as typed
 * @return The message, or null
 */
@Composable
internal fun phoneError(raw: String): String? {
    if (raw.isBlank() || phoneIsValid(raw)) return null
    val digits = raw.count { it.isDigit() }
    return if (digits != LOCAL_DIGITS && digits in 1..LOCAL_DIGITS + 2 && raw.trim().startsWith("0")) {
        stringResource(R.string.phone_digit_count, Numerals.count(digits))
    } else {
        stringResource(R.string.phone_invalid)
    }
}

/**
 * "Batch fee · ৳1,200" with a switch (T8): on, the student pays the
 * batch's fee; off, the fee field asks for this student's own.
 *
 * @param batchFee The batch's fee, formatted
 * @param on Whether the batch fee applies
 * @param onChange Called with the switch's new position
 */
@Composable
private fun BatchFeeToggle(batchFee: String, on: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .toggleable(value = on, role = Role.Switch, onValueChange = onChange)
            .padding(vertical = 4.dp)
            .testTag(TAG_FORM_BATCH_FEE),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(stringResource(R.string.student_add_batch_fee, batchFee), style = MaterialTheme.typography.titleSmall)
            Text(
                stringResource(R.string.student_add_batch_fee_help),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Switch(checked = on, onCheckedChange = null)
    }
}

/**
 * The fee typed for this one student; blank inherits the batch's.
 *
 * @param fee What was typed
 * @param onChange Called with the new text
 */
@Composable
private fun FeeField(fee: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = fee,
        onValueChange = onChange,
        label = { Text(stringResource(R.string.student_add_fee)) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        isError = !feeIsValid(fee),
        supportingText = {
            Text(
                stringResource(
                    if (feeIsValid(fee)) R.string.fee_inherits else R.string.fee_invalid,
                ),
            )
        },
        modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_FEE),
    )
}

/** A Bangladeshi mobile number's digits, written locally. */
private const val LOCAL_DIGITS = 11

/**
 * Add a student to a class.
 *
 * **An empty fee field means INHERIT, not zero** [AC2.2.5]. The field
 * sends null when blank rather than "0.00", because zero is a waiver
 * and defaulting to it would silently waive every student's fee.
 *
 * @param onAdd Called with name, the student's phone, the guardian's
 *   phone or null, and the fee in canonical form or null
 * @param onCancel Called when the teacher backs out
 * @param modifier The layout modifier
 * @param saving True while the write is in flight
 * @param error Why the last write failed, already resolved, or null
 * @param onAddNext Called like [onAdd] by "Save & add next" (T8), or
 *   null to offer only the one save
 * @param existingNames The batch's students, for the same-name hint
 * @param batchFee The batch's monthly fee, formatted, or null when it
 *   has none: with one, the form offers it as a toggle (T8) and the
 *   field appears only for a different fee
 */
@Composable
fun StudentAddForm(
    onAdd: (String, String, String?, String?) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
    saving: Boolean = false,
    error: String? = null,
    onAddNext: ((String, String, String?, String?) -> Unit)? = null,
    existingNames: List<String> = emptyList(),
    batchFee: String? = null,
) {
    var phone by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var guardian by remember { mutableStateOf("") }
    var typedFee by remember { mutableStateOf("") }
    var useBatchFee by remember { mutableStateOf(true) }
    // Blank is INHERIT: with the toggle on, nothing typed is sent.
    val fee = if (batchFee != null && useBatchFee) "" else typedFee
    val guardianOk = guardian.isBlank() || phoneIsValid(guardian)

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // **The student's number comes first, as T8 draws it.** It is
        // what links this seat to the student's own account; without it
        // the student could never reach their seat, which is how this
        // form shipped.
        // **The shared `+88` field** (T8), checked as the teacher types:
        // a ten-digit number is caught before a round trip.
        PhoneNumberField(
            value = phone,
            onValueChange = { phone = it },
            label = stringResource(R.string.student_add_student_phone),
            help = stringResource(R.string.student_add_student_phone_help),
            error = phoneError(phone),
            fieldModifier = Modifier.testTag(TAG_FORM_STUDENT_PHONE),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            label = { Text(stringResource(R.string.student_add_name)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_NAME),
        )
        // **A hint, never a block** (T8): two students can share a name,
        // and the server decides what a seat is. This only saves the
        // teacher adding the same child twice by accident.
        existingNames.firstOrNull { it.trim().equals(name.trim(), ignoreCase = true) && name.isNotBlank() }?.let {
            Text(
                stringResource(R.string.student_add_same_name, it),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.testTag(TAG_FORM_SAME_NAME),
            )
        }
        PhoneNumberField(
            value = guardian,
            onValueChange = { guardian = it },
            label = stringResource(R.string.student_add_guardian),
            error = phoneError(guardian),
            fieldModifier = Modifier.testTag(TAG_FORM_GUARDIAN),
            modifier = Modifier.fillMaxWidth(),
        )
        batchFee?.let { BatchFeeToggle(it, useBatchFee) { on -> useBatchFee = on } }
        if (batchFee == null || !useBatchFee) FeeField(typedFee) { typedFee = it }

        // **Shown on the form, beside what was typed.** The form used
        // to close before the server answered, so a refusal had nowhere
        // to appear and was overwritten by a list reload.
        error?.let {
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.testTag(TAG_FORM_ERROR),
            )
        }

        val ready = !saving && name.isNotBlank() && phoneIsValid(phone) && guardianOk && feeIsValid(fee)
        val send = { to: (String, String, String?, String?) -> Unit ->
            to(name.trim(), phone.trim(), guardian.trim().ifBlank { null }, canonicalFee(fee))
        }
        onAddNext?.let { next ->
            OutlinedButton(
                onClick = { send(next) },
                enabled = ready,
                modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_SUBMIT_NEXT),
            ) {
                Text(stringResource(R.string.student_add_submit_next))
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = { send(onAdd) },
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
