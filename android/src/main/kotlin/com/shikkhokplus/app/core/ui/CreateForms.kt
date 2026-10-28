package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.model.Money

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

/** The guardian phone field on the student form. */
const val TAG_FORM_GUARDIAN: String = "form_guardian"

/** The submit button. */
const val TAG_FORM_SUBMIT: String = "form_submit"

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
 * Create a class.
 *
 * **Client-side validation is FORMAT only, never policy** [layering
 * rules]. The submit button is disabled until a name exists, which is
 * an optimization so the teacher is not sent on a round trip to learn
 * a field is blank — and the server rejects a blank name too. A client
 * check with no server counterpart would be a business rule living on
 * the client.
 *
 * @param onCreate Called with the entered values, the fee already in
 *   canonical form
 * @param onCancel Called when the teacher backs out
 * @param modifier The layout modifier
 * @param saving True while the write is in flight; the form stays open
 *   and cannot submit twice
 * @param error Why the last write failed, already resolved to text, or
 *   null. The typed values stay in the fields beside it
 */
@Composable
fun BatchCreateForm(
    onCreate: (String, List<String>, String?, Int?) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
    saving: Boolean = false,
    error: String? = null,
) {
    var name by remember { mutableStateOf("") }
    var subjects by remember { mutableStateOf("") }
    var fee by remember { mutableStateOf("") }
    var dueDay by remember { mutableStateOf("") }

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
                        dueDayIsValid(dueDay),
                modifier = Modifier.testTag(TAG_FORM_SUBMIT),
            ) {
                Text(stringResource(R.string.batch_create_submit))
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
 */
@Composable
fun StudentAddForm(
    onAdd: (String, String, String?, String?) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
    saving: Boolean = false,
    error: String? = null,
) {
    var phone by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var guardian by remember { mutableStateOf("") }
    var fee by remember { mutableStateOf("") }
    val guardianOk = guardian.isBlank() || phoneIsValid(guardian)

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // **The student's number comes first, as T8 draws it.** It is
        // what links this seat to the student's own account; without it
        // the student could never reach their seat, which is how this
        // form shipped.
        OutlinedTextField(
            value = phone,
            onValueChange = { phone = it },
            label = { Text(stringResource(R.string.student_add_student_phone)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            isError = phone.isNotBlank() && !phoneIsValid(phone),
            supportingText = {
                Text(
                    stringResource(
                        if (phone.isBlank() || phoneIsValid(phone)) {
                            R.string.student_add_student_phone_help
                        } else {
                            R.string.phone_invalid
                        },
                    ),
                )
            },
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_STUDENT_PHONE),
        )
        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            label = { Text(stringResource(R.string.student_add_name)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_NAME),
        )
        OutlinedTextField(
            value = guardian,
            onValueChange = { guardian = it },
            label = { Text(stringResource(R.string.student_add_guardian)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            isError = !guardianOk,
            supportingText =
                if (guardianOk) {
                    null
                } else {
                    { Text(stringResource(R.string.phone_invalid)) }
                },
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_GUARDIAN),
        )
        OutlinedTextField(
            value = fee,
            onValueChange = { fee = it },
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
                    onAdd(
                        name.trim(),
                        phone.trim(),
                        guardian.trim().ifBlank { null },
                        canonicalFee(fee),
                    )
                },
                enabled =
                    !saving &&
                        name.isNotBlank() &&
                        phoneIsValid(phone) &&
                        guardianOk &&
                        feeIsValid(fee),
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
