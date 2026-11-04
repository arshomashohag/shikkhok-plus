package com.shikkhokplus.app.feature.profile.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.MenuCard
import com.shikkhokplus.app.core.designsystem.MenuDivider
import com.shikkhokplus.app.core.designsystem.MenuIcons
import com.shikkhokplus.app.core.designsystem.MenuRow
import com.shikkhokplus.app.core.designsystem.MenuSectionHeader
import com.shikkhokplus.app.core.designsystem.MenuTrailing
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ProfileCard
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.profile.ProfileSummary
import com.shikkhokplus.app.feature.profile.ProfileUiState

/** Test tag for the self-authored name field. */
const val TAG_PROFILE_NAME: String = "profile_name"

/** Test tag for the address field. */
const val TAG_PROFILE_ADDRESS: String = "profile_address"

/** Test tag for the save control. */
const val TAG_PROFILE_SAVE: String = "profile_save"

/** The read-only sign-in number, on Edit profile. */
const val TAG_PROFILE_PHONE: String = "profile_phone"

/** The profile card at the top of More. */
const val TAG_PROFILE_CARD: String = "profile_card"

/** The Edit pill on the profile card. */
const val TAG_PROFILE_EDIT: String = "profile_edit"

/** The delete-account row (O5). */
const val TAG_PROFILE_DELETE: String = "profile_delete"

/** The log-out row. */
const val TAG_PROFILE_SIGN_OUT: String = "profile_sign_out"

/** The teacher's "Where students pay" row. */
const val TAG_PROFILE_PAYMENT_METHODS: String = "profile_payment_methods"

/** The money reports row, shown to a teacher. */
const val TAG_PROFILE_COLLECTIONS: String = "profile_collections"

/** The switch-role row. Absent for a person with one lens. */
const val TAG_PROFILE_SWITCH_LENS: String = "profile_switch_lens"

/** The invitations row, shown to a student and a guardian. */
const val TAG_PROFILE_INVITATIONS: String = "profile_invitations"

/** The guardian's "My children" row. */
const val TAG_PROFILE_MY_CHILDREN: String = "profile_my_children"

/**
 * Where each row of More leads.
 *
 * **A null destination draws no row.** The rows a lens shows are the
 * rows its route supplies, so a student is never offered a teacher's
 * payment methods and nobody is offered a row that opens nothing. Rows
 * the design draws for settings that do not exist yet (notifications,
 * theme, text size, help) are absent for the same reason: a row that
 * opens nothing is worse than no row.
 *
 * @property onEdit Opens Edit profile
 * @property onSignOut Starts logging out (the route confirms first)
 * @property onDeleteAccount Opens the deletion confirmation
 * @property onRetry Repeats a failed read, when the server allows it
 * @property onSwitchLens Returns to the lens picker, or null when this
 *   person holds one lens and has nothing to switch to
 * @property onPaymentMethods Opens "Where students pay", or null
 * @property onCollections Opens the money reports (M1), or null
 * @property onInvitations Opens the invitations list, or null
 * @property onMyChildren Opens the guardian's children, or null
 */
data class MoreActions(
    val onEdit: () -> Unit = {},
    val onSignOut: () -> Unit = {},
    val onDeleteAccount: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onSwitchLens: (() -> Unit)? = null,
    val onPaymentMethods: (() -> Unit)? = null,
    val onCollections: (() -> Unit)? = null,
    val onInvitations: (() -> Unit)? = null,
    val onMyChildren: (() -> Unit)? = null,
)

/**
 * More (T9 teacher, S4 student, G4 guardian), the account half of `O5`.
 *
 * **One screen, three lenses.** The artboards draw the same structure
 * for everyone — a profile card, then cards of rows under small section
 * headers, then the account rows and the version — and differ only in
 * which rows appear. [MoreActions] decides that, so the lens never
 * reaches into the layout.
 *
 * **Editing is its own screen** (S4 "Edit profile"), pushed over this
 * one. While it is open the state is `Editing` or `Saving`, and this
 * screen keeps drawing from [summary], the last profile the server
 * confirmed, so the card does not change under a half-typed name.
 *
 * What a person writes about themselves **changes no teacher's roster**
 * [BR3.1, AC1.5.3]. That note lives on Edit profile, where the change is
 * made, rather than here, where nothing is changed.
 *
 * @param state What to render
 * @param actions Where each row leads; see [MoreActions]
 * @param modifier Layout modifier from the caller
 * @param lens The lens in use, for the role on the card, or null
 * @param summary The last confirmed profile, used while the form is open
 * @param version The app version for the footer, or null for none
 * @param bottomBar The navigation bar, supplied by the route so this
 *   screen stays renderable in a test without one
 * @param onBack Called by the back arrow when More was pushed (a family
 *   home's profile button), or null when it is a tab
 */
@Composable
fun ProfileScreen(
    state: ProfileUiState,
    actions: MoreActions,
    modifier: Modifier = Modifier,
    lens: Lens? = null,
    summary: ProfileSummary? = null,
    version: String? = null,
    bottomBar: @Composable () -> Unit = {},
    onBack: (() -> Unit)? = null,
) {
    ScreenScaffold(
        title = stringResource(R.string.profile_title),
        modifier = modifier,
        bottomBar = bottomBar,
        onBack = onBack,
    ) {
        when (state) {
            ProfileUiState.Loading -> LogoLoader()

            is ProfileUiState.Failed -> {
                Text(
                    text = stringResource(MessageKeys.resolve(state.messageKey)),
                    color = MaterialTheme.colorScheme.error,
                )
                if (state.retryable) {
                    PrimaryButton(
                        text = stringResource(R.string.auth_retry),
                        onClick = actions.onRetry,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }

            else -> {
                if (state is ProfileUiState.Saved) {
                    Banner(title = stringResource(R.string.profile_saved), tone = BannerTone.NEUTRAL)
                }
                MoreMenu(
                    profile = profileOf(state, summary),
                    lens = lens,
                    actions = actions,
                    version = version,
                )
            }
        }
    }
}

/**
 * The profile to draw the card from.
 *
 * A read or a save carries the profile itself; an open form does not,
 * so it falls back to the last confirmed one.
 *
 * @param state The screen state
 * @param summary The last confirmed profile, or null
 * @return The profile, or an empty one when nothing is known
 */
internal fun profileOf(state: ProfileUiState, summary: ProfileSummary?): ProfileSummary =
    when (state) {
        is ProfileUiState.Viewing -> ProfileSummary(state.selfName, state.address, state.phone)
        is ProfileUiState.Saved -> ProfileSummary(state.selfName, state.address, state.phone ?: summary?.phone)
        else -> summary ?: ProfileSummary(selfName = null, address = null, phone = null)
    }

/**
 * The card and the rows.
 *
 * @param profile Who is signed in
 * @param lens The lens in use, or null
 * @param actions Where each row leads
 * @param version The app version, or null
 */
@Composable
private fun MoreMenu(
    profile: ProfileSummary,
    lens: Lens?,
    actions: MoreActions,
    version: String?,
) {
    val name = profile.selfName?.takeIf { it.isNotBlank() }
    val phone = profile.phone?.let(Numerals::phone)
    val role = lens?.let { stringResource(roleLabel(it)) }
    ProfileCard(
        initial = name?.trim()?.take(1)?.uppercase() ?: "?",
        name = name ?: stringResource(R.string.more_name_missing),
        line = listOfNotNull(role, phone).let { parts ->
            if (parts.size == 2) {
                stringResource(R.string.more_role_line, parts[0], parts[1])
            } else {
                parts.firstOrNull().orEmpty()
            }
        },
        onEdit = actions.onEdit,
        editLabel = stringResource(R.string.profile_edit),
        editTag = TAG_PROFILE_EDIT,
        modifier = Modifier.testTag(TAG_PROFILE_CARD),
    )

    PeopleRows(lens, actions)
    TeacherRows(actions)
    AccountRows(actions)

    version?.let {
        Text(
            text = stringResource(R.string.more_version, it),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(bottom = Spacing.screen),
        )
    }
}

/**
 * The student's and guardian's rows: invitations, and a guardian's
 * children (S4, G4). Drawn only when the route supplies them.
 *
 * @param lens The lens in use, for the invitations sub-label
 * @param actions Where each row leads
 */
@Composable
private fun PeopleRows(lens: Lens?, actions: MoreActions) {
    if (actions.onInvitations == null && actions.onMyChildren == null) return
    MenuCard {
        actions.onInvitations?.let { open ->
            MenuRow(
                title = stringResource(R.string.more_invitations),
                subtitle =
                    stringResource(
                        if (lens == Lens.GUARDIAN) {
                            R.string.more_invitations_sub_guardian
                        } else {
                            R.string.more_invitations_sub_student
                        },
                    ),
                icon = MenuIcons.Envelope,
                onClick = open,
                modifier = Modifier.testTag(TAG_PROFILE_INVITATIONS),
            )
        }
        actions.onMyChildren?.let { open ->
            if (actions.onInvitations != null) MenuDivider()
            MenuRow(
                title = stringResource(R.string.more_my_children),
                icon = MenuIcons.Children,
                onClick = open,
                modifier = Modifier.testTag(TAG_PROFILE_MY_CHILDREN),
            )
        }
    }
}

/**
 * The teacher's GETTING PAID and YOUR RECORDS sections (T9).
 *
 * @param actions Where each row leads
 */
@Composable
private fun TeacherRows(actions: MoreActions) {
    actions.onPaymentMethods?.let { open ->
        MenuSection(stringResource(R.string.more_section_getting_paid)) {
            MenuRow(
                title = stringResource(R.string.more_where_students_pay),
                subtitle = stringResource(R.string.more_where_students_pay_sub),
                icon = MenuIcons.Phone,
                onClick = open,
                modifier = Modifier.testTag(TAG_PROFILE_PAYMENT_METHODS),
            )
        }
    }
    actions.onCollections?.let { open ->
        MenuSection(stringResource(R.string.more_section_records)) {
            MenuRow(
                title = stringResource(R.string.profile_collections),
                subtitle = stringResource(R.string.more_collections_sub),
                icon = MenuIcons.Download,
                onClick = open,
                modifier = Modifier.testTag(TAG_PROFILE_COLLECTIONS),
            )
        }
    }
}

/**
 * ACCOUNT: switch role, log out and delete account.
 *
 * **Switch role is absent, not disabled, for a single-lens person.** A
 * greyed-out row tells someone with one role that they are missing
 * something; nothing to switch to is better said by saying nothing.
 *
 * Log out and delete act through a confirmation, so they end in no
 * chevron. Delete is drawn in the error colour and is never a filled
 * control: the destructive step is the confirmation that follows (O5).
 *
 * @param actions Where each row leads
 */
@Composable
private fun AccountRows(actions: MoreActions) {
    MenuSection(stringResource(R.string.more_section_account)) {
        actions.onSwitchLens?.let { switch ->
            MenuRow(
                title = stringResource(R.string.lens_switch),
                icon = MenuIcons.Switch,
                onClick = switch,
                modifier = Modifier.testTag(TAG_PROFILE_SWITCH_LENS),
            )
            MenuDivider()
        }
        MenuRow(
            title = stringResource(R.string.more_log_out),
            icon = MenuIcons.LogOut,
            trailing = MenuTrailing.None,
            onClick = actions.onSignOut,
            modifier = Modifier.testTag(TAG_PROFILE_SIGN_OUT),
        )
        MenuDivider()
        MenuRow(
            title = stringResource(R.string.more_delete_account),
            icon = MenuIcons.Delete,
            trailing = MenuTrailing.None,
            destructive = true,
            onClick = actions.onDeleteAccount,
            modifier = Modifier.testTag(TAG_PROFILE_DELETE),
        )
    }
}

/**
 * A section header over one card of rows.
 *
 * @param header The header text
 * @param rows The rows in the card
 */
@Composable
private fun MenuSection(header: String, rows: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        MenuSectionHeader(header)
        MenuCard { rows() }
    }
}

/**
 * The role word on the profile card.
 *
 * Reuses the sign-up board's role labels so the word a person picked at
 * sign-up is the word they see here.
 *
 * @param lens The lens in use
 * @return The string resource naming it
 */
internal fun roleLabel(lens: Lens): Int =
    when (lens) {
        Lens.TEACHER -> R.string.signup_role_teacher
        Lens.STUDENT -> R.string.signup_role_student
        Lens.GUARDIAN -> R.string.signup_role_guardian
    }
