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

/** Stable test identifiers. Not user-visible text. */
const val TAG_FORM_NAME: String = "form_name"

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
 * @param onCreate Called with the entered values
 * @param onCancel Called when the teacher backs out
 * @param modifier The layout modifier
 */
@Composable
fun BatchCreateForm(
    onCreate: (String, List<String>, String?, Int?) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var name by remember { mutableStateOf("") }
    var subjects by remember { mutableStateOf("") }
    var fee by remember { mutableStateOf("") }
    var dueDay by remember { mutableStateOf("") }

    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            stringResource(R.string.batch_create_title),
            style = MaterialTheme.typography.titleLarge,
        )

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
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_FEE),
        )
        OutlinedTextField(
            value = dueDay,
            onValueChange = { dueDay = it.filter(Char::isDigit).take(2) },
            label = { Text(stringResource(R.string.batch_create_due_day)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth(),
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    onCreate(
                        name.trim(),
                        splitSubjects(subjects),
                        fee.trim().ifBlank { null },
                        dueDay.trim().toIntOrNull(),
                    )
                },
                enabled = name.isNotBlank(),
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
 * Add a student to a class.
 *
 * **An empty fee field means INHERIT, not zero** [AC2.2.5]. The field
 * sends null when blank rather than "0.00", because zero is a waiver
 * and defaulting to it would silently waive every student's fee.
 *
 * @param onAdd Called with the entered values
 * @param onCancel Called when the teacher backs out
 * @param modifier The layout modifier
 */
@Composable
fun StudentAddForm(
    onAdd: (String, String?, String?) -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var name by remember { mutableStateOf("") }
    var guardian by remember { mutableStateOf("") }
    var fee by remember { mutableStateOf("") }

    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            stringResource(R.string.student_add_title),
            style = MaterialTheme.typography.titleLarge,
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
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_GUARDIAN),
        )
        OutlinedTextField(
            value = fee,
            onValueChange = { fee = it },
            label = { Text(stringResource(R.string.student_add_fee)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            supportingText = { Text(stringResource(R.string.fee_inherits)) },
            modifier = Modifier.fillMaxWidth().testTag(TAG_FORM_FEE),
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    onAdd(
                        name.trim(),
                        guardian.trim().ifBlank { null },
                        fee.trim().ifBlank { null },
                    )
                },
                enabled = name.isNotBlank(),
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
