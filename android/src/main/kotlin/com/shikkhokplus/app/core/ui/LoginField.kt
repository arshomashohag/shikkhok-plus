package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField

/** The longest login the sign-in request accepts (`PasswordSignInRequest.login`). */
private const val LOGIN_MAX: Int = 254

/**
 * The sign-in field: "Username, phone or email" [FR4.1, W3].
 *
 * **One free-text field, judged by nobody here** [NFR1.2, FR11.3]. No
 * toggle, no shape check, no classification: the server decides whether
 * the text is a username, a number or an address. A text keyboard,
 * because a username is the common case and a phone keyboard would hide
 * the letters. The autofill hint is `Username`, so a password manager can
 * fill a saved username or a saved phone or email entry; nothing is read
 * from the SIM [NFR3.7].
 *
 * @param value What is typed
 * @param onValueChange Called on each edit
 * @param modifier The layout modifier
 * @param fieldModifier The field's own modifier, for its test tag
 * @param error A refusal shown under the field, or null
 * @param enabled Whether it can be changed
 */
@Composable
fun LoginField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    fieldModifier: Modifier = Modifier,
    error: String? = null,
    enabled: Boolean = true,
) {
    val change: (String) -> Unit = { onValueChange(it.take(LOGIN_MAX)) }
    ShikkhokTextField(
        value = value,
        onValueChange = change,
        label = stringResource(R.string.auth_login_label),
        modifier = modifier,
        error = error,
        enabled = enabled,
        large = true,
        keyboardOptions =
            KeyboardOptions(
                keyboardType = KeyboardType.Text,
                imeAction = ImeAction.Next,
                autoCorrectEnabled = false,
            ),
        fieldModifier = fieldModifier.autofill(AutofillHint.USERNAME, onFill = change),
    )
}
