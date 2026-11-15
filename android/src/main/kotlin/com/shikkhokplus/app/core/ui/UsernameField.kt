package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField

/**
 * The longest username any request accepts: the schema's `maxLength`
 * on every request that carries one (`SignupRequest`, `VerifyRequest`,
 * `UsernameAvailabilityRequest`, `UsernameChangeRequest`).
 *
 * **Not FR1's limit**, which is the server's to apply [FR11.3, NFR3.9]:
 * a longer name is typed, sent, and refused with its own key.
 */
const val USERNAME_MAX_INPUT: Int = 64

/**
 * Whether an edit to a username field is taken.
 *
 * **The cap is on the trimmed text** (functional-spec W1 step 1), because
 * the trimmed text is what is sent: a 64-character name with spaces round
 * it is a 64-character name, and refusing it would refuse a value the
 * server accepts.
 *
 * @param edited The field's text after the edit
 * @return True when the field should take it
 */
internal fun usernameEditAccepted(edited: String): Boolean = edited.trim().length <= USERNAME_MAX_INPUT

/**
 * A username field: one line, a text keyboard, no autocorrect and no
 * capitalisation, and the platform autofill hint the caller names.
 *
 * **Format only** [NFR3.9]: nothing here checks the username rules. The
 * field takes an edit only while the trimmed text fits the schema's
 * length; everything else is the server's to refuse.
 *
 * @param value What is typed
 * @param onValueChange Called with an accepted edit
 * @param label The field's label
 * @param autofill [AutofillHint.USERNAME] for an existing name,
 *   [AutofillHint.NEW_USERNAME] for one being created [TSD-4]
 * @param modifier The layout modifier
 * @param fieldModifier The field's own modifier, for its test tag
 * @param help The line under the field while it is empty, or null
 * @param error A refusal shown under the field, or null
 * @param enabled Whether it can be changed
 */
@Composable
fun UsernameField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    autofill: AutofillHint,
    modifier: Modifier = Modifier,
    fieldModifier: Modifier = Modifier,
    help: String? = null,
    error: String? = null,
    enabled: Boolean = true,
) {
    val change: (String) -> Unit = { if (usernameEditAccepted(it)) onValueChange(it) }
    ShikkhokTextField(
        value = value,
        onValueChange = change,
        label = label,
        modifier = modifier,
        help = help,
        error = error,
        enabled = enabled,
        keyboardOptions =
            KeyboardOptions(
                keyboardType = KeyboardType.Text,
                capitalization = KeyboardCapitalization.None,
                imeAction = ImeAction.Next,
                autoCorrectEnabled = false,
            ),
        fieldModifier = fieldModifier.autofill(autofill, onFill = change),
    )
}
