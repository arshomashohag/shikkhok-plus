package com.shikkhokplus.app.feature.auth.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.BrandMark
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.PromptLink
import com.shikkhokplus.app.core.designsystem.RoleIcons
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.core.ui.PhoneNumberField
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.auth.SignupStateMapper
import com.shikkhokplus.app.feature.auth.SignupUiState

/** Test tag for the phone field, stable across locales. */
const val TAG_SIGNUP_PHONE: String = "signup_phone"

/** Test tag for the name field. */
const val TAG_SIGNUP_NAME: String = "signup_name"

/** Test tag for the address field. */
const val TAG_SIGNUP_ADDRESS: String = "signup_address"

/** Test tag for the submit control. */
const val TAG_SIGNUP_SUBMIT: String = "signup_submit"

/** Test tag for the role card group. */
const val TAG_SIGNUP_ROLE_GROUP: String = "signup_role_group"

/** Test tag for the progress shown while the account is created. */
const val TAG_SIGNUP_SUBMITTING: String = "signup_submitting"

/**
 * `O1`, signup.
 *
 * **This composable renders a [SignupUiState] and nothing else.** There
 * is no conditional here that depends on a domain value: whether a
 * number was already added, whether a role is locked, whether a failure
 * can be retried are all decided by `SignupStateMapper` from what the
 * server said [TC-9, D-31].
 *
 * **The board's layout, top to bottom**: the mark beside "Create
 * account", then the role as three cards, then name, number and
 * address with a help line each, and a bar pinned to the foot holding
 * "Send code" and the way to log in. A number a teacher already added
 * puts the number before the name, as the board does, because the name
 * was filled in from it.
 *
 * Two of this unit's rules are visible as *absences* in the code below,
 * which is why they are named here:
 *
 * * **The already-added notice names neither the teacher nor the
 *   batch** [BR2.3, AC1.12.2]. [SignupUiState.AlreadyAdded] holds
 *   neither value, so there is nothing here that could leak one even
 *   by accident. The board's example names both; that is the one place
 *   the board is not followed.
 * * **The role is locked, not hidden** [BR4.5, AC1.12.1]. A person
 *   whose teacher added them sees which role the seat carries and
 *   cannot change it; hiding the control would leave them unable to
 *   tell whether the system understood them.
 *
 * The address stays optional, by the person's decision, so the board's
 * "Add your address" refusal is not drawn.
 *
 * @param state What to render
 * @param onSubmit Called with the whole payload, on the button
 * @param onGoToLogin Called from "Log in"
 * @param onRetry Called when a retryable failure offers a retry
 * @param modifier Layout modifier from the caller
 * @param onLookup Called when the number field is left holding a
 *   well-formed number, to ask whether a teacher already added it
 * @param onNumberEdited Called on each edit of the number, so an answer
 *   given for the previous number stops applying to this one
 */
@Composable
fun SignupScreen(
    state: SignupUiState,
    onSubmit: (phone: String, name: String, address: String, role: SignupRole) -> Unit,
    onGoToLogin: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    onLookup: (String) -> Unit = {},
    onNumberEdited: () -> Unit = {},
) {
    var phone by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var address by remember { mutableStateOf("") }

    // **Nothing chosen at first**, as the board draws it: a preselected
    // role is one the person may submit without having chosen.
    var chosenRole by remember { mutableStateOf<SignupRole?>(null) }

    // The already-added answer outlives the states that follow it, so a
    // form submitted from it keeps its locked role while it submits or
    // fails. A new number (Empty) forgets it.
    var added by remember { mutableStateOf<SignupUiState.AlreadyAdded?>(null) }
    when (state) {
        is SignupUiState.AlreadyAdded -> added = state
        SignupUiState.Empty, SignupUiState.CheckingNumber -> added = null
        else -> Unit
    }
    val prefilled = added
    LaunchedEffect(prefilled?.prefilledName) {
        // Seeded once from the teacher's name, then the person's own
        // edits win [AC1.12.2: "You can correct it"].
        prefilled?.let { name = it.prefilledName }
    }

    val role = prefilled?.lockedRole ?: chosenRole
    val failure = state as? SignupUiState.Failed
    val alreadyRegistered = failure?.messageKey == ALREADY_REGISTERED_KEY

    Surface(modifier = modifier.fillMaxSize(), color = MaterialTheme.colorScheme.surface) {
        BoxWithConstraints(Modifier.fillMaxSize()) {
            val minHeight = maxHeight
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                Column(
                    modifier = Modifier.fillMaxWidth().heightIn(min = minHeight),
                    verticalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column {
                        Header()
                        Form(
                            state = state,
                            prefilled = prefilled,
                            phone = phone,
                            onPhoneChange = {
                                phone = it
                                onNumberEdited()
                            },
                            onPhoneLeft = onLookup,
                            name = name,
                            onNameChange = { name = it },
                            address = address,
                            onAddressChange = { address = it },
                            role = role,
                            onRoleChange = { chosenRole = it },
                            alreadyRegistered = alreadyRegistered,
                            onGoToLogin = onGoToLogin,
                            onRetry = onRetry,
                        )
                    }
                    Bar(
                        phone = phone,
                        enabled =
                            role != null && name.isNotBlank() && phone.isNotBlank() &&
                                state != SignupUiState.Submitting,
                        offerLogin = prefilled == null && !alreadyRegistered,
                        onSubmit = {
                            role?.let {
                                onSubmit(phone, name.ifEmpty { prefilled?.prefilledName.orEmpty() }, address, it)
                            }
                        },
                        onGoToLogin = onGoToLogin,
                    )
                }
            }
        }

        // **Over the form, centred on the window**, by the app-wide rule
        // for a loader; the board's form stays visible beneath it.
        if (state == SignupUiState.Submitting) {
            LogoLoader(
                modifier = Modifier.testTag(TAG_SIGNUP_SUBMITTING),
                size = 72.dp,
                label = stringResource(R.string.signup_submitting),
            )
        }
    }
}

/** The O1 `.top` band: the mark beside the title. */
@Composable
private fun Header() {
    Row(
        modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        BrandMark(size = 40.dp)
        Text(
            text = stringResource(R.string.signup_title),
            style = MaterialTheme.typography.headlineMedium.copy(fontSize = 24.sp, lineHeight = 36.sp),
        )
    }
}

/**
 * The form: any notice, the role cards, and the three fields.
 *
 * @param state What to render
 * @param prefilled The already-added answer, while it applies
 * @param phone The number typed so far
 * @param onPhoneChange Called on each edit of the number
 * @param onPhoneLeft Called when the number field is left holding a valid number
 * @param name The name field's value
 * @param onNameChange Called on each edit of the name
 * @param address The address field's value
 * @param onAddressChange Called on each edit of the address
 * @param role The selected role, or null before one is chosen
 * @param onRoleChange Called when a role card is chosen
 * @param alreadyRegistered Whether the server refused the number as taken
 * @param onGoToLogin Called from the taken number's "Log in"
 * @param onRetry Called when a retryable failure offers a retry
 */
@Composable
private fun Form(
    state: SignupUiState,
    prefilled: SignupUiState.AlreadyAdded?,
    phone: String,
    onPhoneChange: (String) -> Unit,
    onPhoneLeft: (String) -> Unit,
    name: String,
    onNameChange: (String) -> Unit,
    address: String,
    onAddressChange: (String) -> Unit,
    role: SignupRole?,
    onRoleChange: (SignupRole) -> Unit,
    alreadyRegistered: Boolean,
    onGoToLogin: () -> Unit,
    onRetry: () -> Unit,
) {
    // Every message about a field is shown under that field; only a
    // failure that is about no field is a banner above the form.
    val invalidKeys = (state as? SignupUiState.Invalid)?.fieldKeys.orEmpty()
    val failure = state as? SignupUiState.Failed
    val phoneError =
        if (SignupStateMapper.PHONE_KEY in invalidKeys || failure?.messageKey in PHONE_MESSAGE_KEYS) {
            stringResource(R.string.phone_invalid)
        } else {
            null
        }
    val nameError =
        invalidKeys.firstOrNull { it == SignupStateMapper.NAME_KEY }?.let { stringResource(MessageKeys.resolve(it)) }
    val generalFailure = failure?.takeIf { phoneError == null && !alreadyRegistered }

    Column(
        modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Notices(
            codeSent = state is SignupUiState.CodeSent,
            prefilled = prefilled != null,
            failure = generalFailure,
            onRetry = onRetry,
        )

        RolePicker(role = role, locked = prefilled != null, onRoleChange = onRoleChange)

        val nameField: @Composable () -> Unit = {
            ShikkhokTextField(
                value = name,
                onValueChange = onNameChange,
                label = stringResource(R.string.signup_name_label),
                help =
                    when {
                        prefilled != null -> stringResource(R.string.signup_name_help_prefilled)
                        name.isEmpty() -> stringResource(R.string.signup_name_help)
                        else -> null
                    },
                error = nameError,
                fieldModifier = Modifier.testTag(TAG_SIGNUP_NAME),
            )
        }
        val phoneField: @Composable () -> Unit = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                PhoneNumberField(
                    value = phone,
                    onValueChange = onPhoneChange,
                    label = stringResource(R.string.signup_phone_label),
                    help = if (phone.isEmpty()) stringResource(R.string.signup_phone_help) else null,
                    error = phoneError,
                    onLeftWithValidNumber = onPhoneLeft,
                    fieldModifier = Modifier.testTag(TAG_SIGNUP_PHONE),
                )
                // The taken number is named under the number, with the
                // way to log in beside it (O1's error board).
                if (alreadyRegistered) {
                    Banner(
                        title = stringResource(R.string.signup_number_already_registered),
                        tone = BannerTone.ERROR,
                        action = {
                            TextAction(text = stringResource(R.string.signup_log_in), onClick = onGoToLogin)
                        },
                    )
                }
            }
        }
        // A number a teacher added comes first, because the name was
        // filled in from it.
        if (prefilled != null) {
            phoneField()
            nameField()
        } else {
            nameField()
            phoneField()
        }

        ShikkhokTextField(
            value = address,
            onValueChange = onAddressChange,
            label = stringResource(R.string.signup_address_label),
            singleLine = false,
            minLines = 2,
            fieldModifier = Modifier.testTag(TAG_SIGNUP_ADDRESS),
        )
    }
}

/**
 * The banners above the form: code sent, already added, or a failure
 * that is about no one field.
 *
 * @param codeSent Whether the code is on its way
 * @param prefilled Whether a teacher already added this number
 * @param failure A failure to show, or null
 * @param onRetry Called when the failure offers a retry
 */
@Composable
private fun Notices(
    codeSent: Boolean,
    prefilled: Boolean,
    failure: SignupUiState.Failed?,
    onRetry: () -> Unit,
) {
    if (codeSent) {
        Banner(title = stringResource(R.string.signup_code_sent))
    }
    if (prefilled) {
        Banner(
            title = stringResource(R.string.signup_already_added_title),
            body = stringResource(R.string.signup_already_added_notice),
        )
    }
    if (failure != null) {
        Banner(
            title = stringResource(MessageKeys.resolve(failure.messageKey)),
            tone = BannerTone.ERROR,
        )
        if (failure.retryable) {
            SecondaryButton(
                text = stringResource(R.string.auth_retry),
                onClick = onRetry,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

/**
 * "I am a", three role cards, and a line about the chosen role.
 *
 * @param role The selected role, or null
 * @param locked Whether a teacher's seat already fixed it
 * @param onRoleChange Called when a card is chosen
 */
@Composable
private fun RolePicker(
    role: SignupRole?,
    locked: Boolean,
    onRoleChange: (SignupRole) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = stringResource(R.string.signup_role_label),
            style = MaterialTheme.typography.labelLarge,
        )
        Row(
            modifier = Modifier.fillMaxWidth().selectableGroup().testTag(TAG_SIGNUP_ROLE_GROUP),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SignupRole.entries.forEach { option ->
                RoleCard(
                    role = option,
                    selected = option == role,
                    locked = locked,
                    onClick = { onRoleChange(option) },
                    modifier = Modifier.weight(1f),
                )
            }
        }
        if (role != null && !locked) {
            Text(
                text = stringResource(helpOf(role)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * One 84dp role card: an icon above the role's name.
 *
 * Locked, every card is disabled; the chosen one keeps its highlight and
 * the others fade, so the person can still read which role it is.
 *
 * @param role The role this card offers
 * @param selected Whether it is the chosen role
 * @param locked Whether a teacher's seat already fixed the role
 * @param onClick Called when chosen
 * @param modifier The layout modifier
 */
@Composable
private fun RoleCard(
    role: SignupRole,
    selected: Boolean,
    locked: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(12.dp)
    Box(
        modifier =
            modifier
                .height(84.dp)
                .alpha(if (locked && !selected) LOCKED_ALPHA else 1f)
                .background(if (selected) colors.primaryContainer else colors.surface, shape)
                .border(
                    width = if (selected) 2.dp else 1.5.dp,
                    color = if (selected) colors.primary else colors.outlineVariant,
                    shape = shape,
                ).selectable(
                    selected = selected,
                    enabled = !locked,
                    role = Role.RadioButton,
                    onClick = onClick,
                ),
        contentAlignment = Alignment.Center,
    ) {
        val content = if (selected) colors.onPrimaryContainer else colors.onSurface
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Icon(
                imageVector = iconOf(role),
                contentDescription = null,
                tint = content,
                modifier = Modifier.size(26.dp),
            )
            Text(
                text = stringResource(labelOf(role)),
                style = MaterialTheme.typography.bodyMedium.copy(fontSize = 15.sp, lineHeight = 24.sp),
                fontWeight = FontWeight.SemiBold,
                color = content,
            )
        }
    }
}

/**
 * The bar pinned to the foot, under a hairline.
 *
 * @param phone The number, named on the button once typed
 * @param enabled Whether the form can be sent
 * @param offerLogin Whether to show "Already have an account? Log in"
 * @param onSubmit Called from the button
 * @param onGoToLogin Called from "Log in"
 */
@Composable
private fun Bar(
    phone: String,
    enabled: Boolean,
    offerLogin: Boolean,
    onSubmit: () -> Unit,
    onGoToLogin: () -> Unit,
) {
    Column {
        HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
        Column(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 14.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            PrimaryButton(
                // **`signup_submit` takes the number as an argument.**
                // Fetched without one, Android renders the placeholder
                // itself, so the button read "Send code to %1$s" on a
                // device. Before a number is typed there is nothing to
                // name, so the generic label is used until then.
                text =
                    if (phone.isBlank()) {
                        stringResource(R.string.signup_submit_generic)
                    } else {
                        stringResource(R.string.signup_submit, phone)
                    },
                onClick = onSubmit,
                enabled = enabled,
                modifier = Modifier.fillMaxWidth().testTag(TAG_SIGNUP_SUBMIT),
            )
            if (offerLogin) {
                PromptLink(
                    prompt = stringResource(R.string.signup_have_account),
                    link = stringResource(R.string.signup_log_in),
                    onClick = onGoToLogin,
                )
            }
        }
    }
}

/**
 * The string resource naming a role.
 *
 * A `when` rather than a map so a fourth role fails to compile here
 * instead of rendering nothing.
 *
 * @param role The role to label
 * @return Its string resource id
 */
private fun labelOf(role: SignupRole): Int = when (role) {
    SignupRole.TEACHER -> R.string.signup_role_teacher
    SignupRole.STUDENT -> R.string.signup_role_student
    SignupRole.GUARDIAN -> R.string.signup_role_guardian
}

/**
 * The line describing what a role does, under the cards.
 *
 * @param role The chosen role
 * @return Its string resource id
 */
private fun helpOf(role: SignupRole): Int = when (role) {
    SignupRole.TEACHER -> R.string.signup_role_help_teacher
    SignupRole.STUDENT -> R.string.signup_role_help_student
    SignupRole.GUARDIAN -> R.string.signup_role_help_guardian
}

/**
 * The icon on a role's card.
 *
 * @param role The role
 * @return Its icon
 */
private fun iconOf(role: SignupRole): ImageVector = when (role) {
    SignupRole.TEACHER -> RoleIcons.Teacher
    SignupRole.STUDENT -> RoleIcons.Student
    SignupRole.GUARDIAN -> RoleIcons.Guardian
}

/** How far the cards a locked role rules out are faded (O1). */
private const val LOCKED_ALPHA = 0.45f

/** The refusal of a number that already has an account. */
private const val ALREADY_REGISTERED_KEY = "signup.number.already_registered"
