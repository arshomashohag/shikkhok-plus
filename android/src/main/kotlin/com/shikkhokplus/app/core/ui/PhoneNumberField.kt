package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.PhoneField

/**
 * A mobile-number field that checks the number when the person leaves it.
 *
 * **Checked on focus-out, never per keystroke.** Reported from a device:
 * sign-up judged the number on every key press, so the first digit was
 * already "wrong" and the form reacted to a number that was still being
 * typed. A number is only finished when the person moves on, so that is
 * when it is checked.
 *
 * **The message sits under the field and nothing else moves.** The
 * design system's field carries it in its own note line, so a wrong
 * number never replaces or blanks the form around it.
 *
 * Editing clears a message the check left, without checking again: a
 * stale "invalid" under a number being corrected is noise, and a fresh
 * judgement waits for the next focus-out.
 *
 * Format only, through [phoneIsValid]; the server canonicalises and
 * decides [team: Layer boundaries].
 *
 * @param value The number typed so far
 * @param onValueChange Called on each edit
 * @param label The label above the field
 * @param modifier The layout modifier, for the whole field
 * @param fieldModifier Applied to the editable text, for a test tag
 * @param help The line under the field when nothing is wrong
 * @param error A message from outside the field -- a submit-time check
 *   or a server refusal -- shown in place of the field's own
 * @param large The log-in board's larger field
 * @param enabled Whether it can be edited
 * @param onLeftWithValidNumber Called when the person leaves the field
 *   holding a well-formed number
 */
@Composable
fun PhoneNumberField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    fieldModifier: Modifier = Modifier,
    help: String? = null,
    error: String? = null,
    large: Boolean = false,
    enabled: Boolean = true,
    onLeftWithValidNumber: (String) -> Unit = {},
) {
    val focusManager = LocalFocusManager.current
    var hadFocus by remember { mutableStateOf(false) }
    var leftInvalid by remember { mutableStateOf(false) }

    val shown = error ?: if (leftInvalid) stringResource(R.string.phone_invalid) else null

    PhoneField(
        value = value,
        onValueChange = {
            leftInvalid = false
            onValueChange(it)
        },
        label = label,
        modifier = modifier,
        help = help,
        error = shown,
        enabled = enabled,
        large = large,
        // Done leaves the field, which is what checks the number.
        keyboardActions = KeyboardActions(onDone = { focusManager.clearFocus() }),
        fieldModifier =
            fieldModifier.onFocusChanged { focus ->
                if (focus.isFocused) {
                    hadFocus = true
                } else if (hadFocus) {
                    // Only a field the person was in can be "left": the
                    // first composition reports unfocused too, and an
                    // untouched field has nothing to judge.
                    hadFocus = false
                    val wellFormed = value.isNotBlank() && phoneIsValid(value)
                    leftInvalid = value.isNotBlank() && !wellFormed
                    if (wellFormed) onLeftWithValidNumber(value)
                }
            },
    )
}
