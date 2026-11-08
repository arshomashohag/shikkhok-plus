package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.model.EMAIL_MAX
import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.model.emailIsWellFormed

/** The Phone choice of the Phone | Email toggle. */
const val TAG_KIND_PHONE: String = "identifier_kind_phone"

/** The Email choice of the Phone | Email toggle. */
const val TAG_KIND_EMAIL: String = "identifier_kind_email"

/** The Show / Hide control on a password field. */
const val TAG_PASSWORD_VISIBILITY: String = "password_visibility"

/** The longest password the field accepts, as the server does. */
private const val PASSWORD_FIELD_MAX: Int = 128

/**
 * Whether a typed identifier has the shape of its kind: a Bangladeshi
 * mobile number, or an email address.
 *
 * **Format only.** It spares a round trip for an obvious slip; whether
 * an account exists for it is the server's to say [BR2.7].
 *
 * @param identifier What was typed, and which kind
 * @return True when it could be sent
 */
fun identifierIsWellFormed(identifier: Identifier): Boolean =
    when (identifier.kind) {
        IdentifierKind.PHONE -> phoneIsValid(identifier.value)
        IdentifierKind.EMAIL -> emailIsWellFormed(identifier.value)
    }

/**
 * The Phone | Email toggle.
 *
 * **A pair of radio items in a selectable group**, drawn as one
 * two-segment control: the same construction as sign-up's role cards,
 * so TalkBack reads "Phone, selected, radio button, 1 of 2" and a test
 * drives it by touch exactly as a person does.
 *
 * @param kind The kind chosen
 * @param onKindChange Called with the other kind when it is chosen
 * @param modifier The layout modifier
 * @param enabled Whether it can be changed
 */
@Composable
fun IdentifierKindToggle(
    kind: IdentifierKind,
    onKindChange: (IdentifierKind) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val colors = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(10.dp)
    Row(
        modifier =
            modifier
                .fillMaxWidth()
                .heightIn(min = TOGGLE_HEIGHT)
                .border(1.5.dp, colors.outlineVariant, shape)
                .clip(shape)
                .selectableGroup()
                .alpha(if (enabled) 1f else DISABLED_ALPHA),
    ) {
        listOf(
            Triple(IdentifierKind.PHONE, R.string.identifier_kind_phone, TAG_KIND_PHONE),
            Triple(IdentifierKind.EMAIL, R.string.identifier_kind_email, TAG_KIND_EMAIL),
        ).forEach { (option, label, tag) ->
            val selected = option == kind
            Box(
                modifier =
                    Modifier
                        .weight(1f)
                        .heightIn(min = TOGGLE_HEIGHT)
                        .background(if (selected) colors.primaryContainer else colors.surface)
                        .selectable(
                            selected = selected,
                            enabled = enabled,
                            role = Role.RadioButton,
                            onClick = { onKindChange(option) },
                        ).testTag(tag),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = stringResource(label),
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
                    color = if (selected) colors.onPrimaryContainer else colors.onSurface,
                )
            }
        }
    }
}

/** The toggle's height: a comfortable touch target. */
private val TOGGLE_HEIGHT = 48.dp

/** How far a disabled toggle fades, as a locked role card does. */
private const val DISABLED_ALPHA = 0.45f

/**
 * The identifier field: a phone number field or an email field,
 * depending on the toggle above it.
 *
 * **The number is typed, never read from the SIM** [TC-4, D-35]: the
 * phone half is the app's one [PhoneNumberField].
 *
 * @param kind Which kind of identifier is being typed
 * @param value What is typed
 * @param onValueChange Called on each edit
 * @param modifier The layout modifier
 * @param fieldModifier Applied to the editable text, for a test tag
 * @param phoneLabel The label when a number is asked for
 * @param help A line under the box, or null
 * @param error A refusal under the box, or null
 * @param large The log-in board's larger field
 * @param onLeftWithValidNumber Called when a phone field is left holding
 *   a well-formed number; never for an email
 */
@Composable
fun IdentifierField(
    kind: IdentifierKind,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    fieldModifier: Modifier = Modifier,
    phoneLabel: String = stringResource(R.string.auth_phone_label),
    help: String? = null,
    error: String? = null,
    large: Boolean = false,
    onLeftWithValidNumber: (String) -> Unit = {},
) {
    when (kind) {
        IdentifierKind.PHONE ->
            PhoneNumberField(
                value = value,
                onValueChange = onValueChange,
                label = phoneLabel,
                modifier = modifier,
                fieldModifier = fieldModifier,
                help = help,
                error = error,
                large = large,
                onLeftWithValidNumber = onLeftWithValidNumber,
            )
        IdentifierKind.EMAIL ->
            ShikkhokTextField(
                value = value,
                onValueChange = { onValueChange(it.take(EMAIL_MAX)) },
                label = stringResource(R.string.identifier_email_label),
                modifier = modifier,
                help = help,
                error = error,
                placeholder = EMAIL_PLACEHOLDER,
                keyboardOptions =
                    KeyboardOptions(
                        keyboardType = KeyboardType.Email,
                        imeAction = ImeAction.Next,
                        autoCorrectEnabled = false,
                    ),
                fieldModifier =
                    fieldModifier.autofill(AutofillHint.EMAIL, onFill = onValueChange),
                large = large,
            )
    }
}

/**
 * A password field: masked, with Show / Hide, a password keyboard, and
 * the platform's autofill.
 *
 * **What is typed lives in the caller's `remember`, never in saved
 * state**: a password written to a Bundle is a password the platform may
 * write to disk. Showing it is a choice that lasts only while the field
 * is on screen.
 *
 * @param value What is typed
 * @param onValueChange Called on each edit
 * @param label The label above the box
 * @param modifier The layout modifier
 * @param fieldModifier Applied to the editable text, for a test tag
 * @param newPassword True when the person is choosing one, so the
 *   autofill service offers to generate and save it rather than to fill
 * @param help A line under the box, or null
 * @param error A refusal under the box, or null
 * @param enabled Whether it can be edited
 * @param imeAction The keyboard's action key
 * @param onImeAction What it does
 */
@Composable
fun PasswordField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    fieldModifier: Modifier = Modifier,
    newPassword: Boolean = false,
    help: String? = null,
    error: String? = null,
    enabled: Boolean = true,
    imeAction: ImeAction = ImeAction.Done,
    onImeAction: () -> Unit = {},
) {
    var shown by remember { mutableStateOf(false) }
    val change: (String) -> Unit = { onValueChange(it.take(PASSWORD_FIELD_MAX)) }
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
                keyboardType = KeyboardType.Password,
                imeAction = imeAction,
                autoCorrectEnabled = false,
            ),
        // Only Done is taken over; Next keeps its default, moving focus on.
        keyboardActions =
            if (imeAction == ImeAction.Done) KeyboardActions(onDone = { onImeAction() }) else KeyboardActions.Default,
        visualTransformation = if (shown) VisualTransformation.None else PasswordVisualTransformation(),
        fieldModifier =
            fieldModifier.autofill(
                if (newPassword) AutofillHint.NEW_PASSWORD else AutofillHint.PASSWORD,
                onFill = change,
            ),
        trailing = {
            TextAction(
                text = stringResource(if (shown) R.string.password_hide else R.string.password_show),
                onClick = { shown = !shown },
                enabled = enabled,
                modifier = Modifier.testTag(TAG_PASSWORD_VISIBILITY),
            )
        },
    )
}

/**
 * A new password typed twice, with the rule under the first.
 *
 * @param password The first copy
 * @param onPasswordChange Called on each edit of it
 * @param confirm The second copy
 * @param onConfirmChange Called on each edit of it
 * @param modifier The layout modifier
 * @param passwordLabel The first field's label
 * @param error A refusal under the second field, or null
 * @param enabled Whether they can be edited
 * @param passwordTag The first field's test tag
 * @param confirmTag The second field's test tag
 * @param onDone Called from the keyboard's Done on the second field
 */
@Composable
fun NewPasswordFields(
    password: String,
    onPasswordChange: (String) -> Unit,
    confirm: String,
    onConfirmChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    passwordLabel: String = stringResource(R.string.password_new_label),
    error: String? = null,
    enabled: Boolean = true,
    passwordTag: String = TAG_NEW_PASSWORD,
    confirmTag: String = TAG_CONFIRM_PASSWORD,
    onDone: () -> Unit = {},
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        PasswordField(
            value = password,
            onValueChange = onPasswordChange,
            label = passwordLabel,
            newPassword = true,
            help = stringResource(R.string.password_rule),
            enabled = enabled,
            imeAction = ImeAction.Next,
            fieldModifier = Modifier.testTag(passwordTag),
        )
        PasswordField(
            value = confirm,
            onValueChange = onConfirmChange,
            label = stringResource(R.string.password_confirm_label),
            newPassword = true,
            error = error,
            enabled = enabled,
            onImeAction = onDone,
            fieldModifier = Modifier.testTag(confirmTag),
        )
    }
}

/** The first field of [NewPasswordFields], by default. */
const val TAG_NEW_PASSWORD: String = "password_new"

/** The second field of [NewPasswordFields], by default. */
const val TAG_CONFIRM_PASSWORD: String = "password_confirm"

/**
 * The shape of an email address, as a placeholder. Not text to
 * translate: it is the format, the same in every language.
 */
private const val EMAIL_PLACEHOLDER = "name@example.com"
