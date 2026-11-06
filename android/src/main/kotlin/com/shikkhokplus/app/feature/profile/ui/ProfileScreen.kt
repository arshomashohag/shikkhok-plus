package com.shikkhokplus.app.feature.profile.ui

import com.shikkhokplus.app.core.network.WorkspaceDto
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
import androidx.compose.ui.res.pluralStringResource
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

/** The Settings row (APP). */
const val TAG_PROFILE_SETTINGS: String = "profile_settings"

/** The log-out row. */
const val TAG_PROFILE_SIGN_OUT: String = "profile_sign_out"

/** The teacher's "Where students pay" row. */
const val TAG_PROFILE_PAYMENT_METHODS: String = "profile_payment_methods"

/** The money reports row, shown to a teacher. */
const val TAG_PROFILE_COLLECTIONS: String = "profile_collections"

/** The expenses row, shown to a teacher. */
const val TAG_PROFILE_EXPENSES: String = "profile_expenses"

/** The monthly summary row, shown to a teacher. */
const val TAG_PROFILE_MONEY_SUMMARY: String = "profile_money_summary"

/** The open-a-centre row, shown to a teacher. */
const val TAG_PROFILE_OPEN_CENTRE: String = "profile_open_centre"

/** The centre's members row, shown to a teacher in a centre. */
const val TAG_PROFILE_CENTRE_MEMBERS: String = "profile_centre_members"

/** The centre's timetable row, shown to a teacher in a centre. */
const val TAG_PROFILE_CENTRE_TIMETABLE: String = "profile_centre_timetable"

/** The centre's teachers and staff row, shown to a teacher in a centre. */
const val TAG_PROFILE_CENTRE_STAFF: String = "profile_centre_staff"

/** The centres' offers row, shown to a teacher. */
const val TAG_PROFILE_CENTRE_OFFERS: String = "profile_centre_offers"

/**
 * Tag for one workspace row.
 *
 * @param ownerId The workspace
 * @return The tag
 */
fun workspaceRowTag(ownerId: String): String = "profile_workspace_$ownerId"

/** The switch-role row. Absent for a person with one lens. */
const val TAG_PROFILE_SWITCH_LENS: String = "profile_switch_lens"

/** The invitations row, shown to a student and a guardian. */
const val TAG_PROFILE_INVITATIONS: String = "profile_invitations"

/** The offline banner on More. */
const val TAG_PROFILE_OFFLINE: String = "profile_offline"

/** The teacher's "records not sent yet" row. */
const val TAG_PROFILE_UNSENT: String = "profile_unsent"

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
 * @property onExpenses Opens the expense list, or null
 * @property onMoneySummary Opens the monthly summary, or null
 * @property workspaces The workspaces the server offers, solo first;
 *   listed to switch between only when there is more than one
 * @property currentWorkspace The workspace in effect, or null
 * @property onSwitchWorkspace Moves into another workspace, or null
 * @property onOpenCentre Opens a coaching centre, or null
 * @property onCentreMembers Opens the centre's members, or null outside a centre
 * @property onCentreStaff Opens the centre's teachers and staff, or null outside a centre
 * @property onCentreTimetable Opens the centre's timetable, or null outside a centre
 * @property onCentreOffers Opens the centres' offers, or null
 * @property onInvitations Opens the invitations list, or null
 * @property onMyChildren Opens the guardian's children, or null
 * @property unsent How many records this phone has not sent yet (T9)
 * @property onSettings Opens Settings, or null where none are kept
 */
data class MoreActions(
    val onEdit: () -> Unit = {},
    val onSignOut: () -> Unit = {},
    val onDeleteAccount: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onSwitchLens: (() -> Unit)? = null,
    val onPaymentMethods: (() -> Unit)? = null,
    val onCollections: (() -> Unit)? = null,
    val onExpenses: (() -> Unit)? = null,
    val onMoneySummary: (() -> Unit)? = null,
    val workspaces: List<WorkspaceDto> = emptyList(),
    val currentWorkspace: WorkspaceDto? = null,
    val onSwitchWorkspace: ((String) -> Unit)? = null,
    val onOpenCentre: (() -> Unit)? = null,
    val onCentreMembers: (() -> Unit)? = null,
    val onCentreStaff: (() -> Unit)? = null,
    val onCentreTimetable: (() -> Unit)? = null,
    val onCentreOffers: (() -> Unit)? = null,
    val onInvitations: (() -> Unit)? = null,
    val onMyChildren: (() -> Unit)? = null,
    val unsent: Int = 0,
    val onSettings: (() -> Unit)? = null,
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
                val offline = (state as? ProfileUiState.Viewing)?.offline == true
                if (offline) {
                    Banner(
                        title = stringResource(R.string.more_offline_title),
                        body = stringResource(R.string.more_offline_body),
                        tone = BannerTone.NEUTRAL,
                        modifier = Modifier.testTag(TAG_PROFILE_OFFLINE),
                    )
                }
                MoreMenu(
                    profile = profileOf(state, summary),
                    lens = lens,
                    actions = actions,
                    version = version,
                    offline = offline,
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
 * @param offline Whether rows that need the server are shown as waiting
 */
@Composable
private fun MoreMenu(
    profile: ProfileSummary,
    lens: Lens?,
    actions: MoreActions,
    version: String?,
    offline: Boolean = false,
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
        // Editing needs the server to save; offline it is not offered.
        onEdit = actions.onEdit.takeUnless { offline },
        editLabel = stringResource(R.string.profile_edit),
        editTag = TAG_PROFILE_EDIT,
        modifier = Modifier.testTag(TAG_PROFILE_CARD),
    )

    PeopleRows(lens, actions, offline)
    TeacherRows(actions, offline)
    AppRows(actions)
    AccountRows(actions, offline)

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
 * @param offline Whether the rows wait for a connection
 */
@Composable
private fun PeopleRows(lens: Lens?, actions: MoreActions, offline: Boolean) {
    if (actions.onInvitations == null && actions.onMyChildren == null) return
    MenuCard {
        actions.onInvitations?.let { open ->
            MenuRow(
                title = stringResource(R.string.more_invitations),
                subtitle =
                    stringResource(
                        when {
                            offline -> R.string.more_needs_connection
                            lens == Lens.GUARDIAN -> R.string.more_invitations_sub_guardian
                            else -> R.string.more_invitations_sub_student
                        },
                    ),
                icon = MenuIcons.Envelope,
                onClick = open,
                enabled = !offline,
                modifier = Modifier.testTag(TAG_PROFILE_INVITATIONS),
            )
        }
        actions.onMyChildren?.let { open ->
            if (actions.onInvitations != null) MenuDivider()
            MenuRow(
                title = stringResource(R.string.more_my_children),
                subtitle = stringResource(R.string.more_needs_connection).takeIf { offline },
                icon = MenuIcons.Children,
                onClick = open,
                enabled = !offline,
                modifier = Modifier.testTag(TAG_PROFILE_MY_CHILDREN),
            )
        }
    }
}

/**
 * WORKSPACE: which workspace the teacher screens act on, the centre's
 * members while in a centre, opening a centre, and centres' offers.
 *
 * The list is the server's own (`GET /v1/me`), so it offers nothing the
 * server would then refuse; with one workspace there is nothing to list.
 *
 * @param actions Where each row leads
 * @param offline Whether the rows wait for a connection
 */
@Composable
private fun WorkspaceRows(actions: MoreActions, offline: Boolean) {
    val open = actions.onOpenCentre ?: return
    val needs = stringResource(R.string.more_needs_connection)
    MenuSection(stringResource(R.string.workspace_section)) {
        val switch = actions.onSwitchWorkspace
        if (switch != null && actions.workspaces.size > 1) {
            actions.workspaces.forEach { workspace ->
                val here = workspace.ownerId == actions.currentWorkspace?.ownerId
                MenuRow(
                    title =
                        if (workspace.isCentre) {
                            Numerals.freeText(workspace.name.orEmpty())
                        } else {
                            stringResource(R.string.workspace_solo)
                        },
                    subtitle = stringResource(if (here) R.string.workspace_current else R.string.workspace_switch),
                    icon = MenuIcons.Switch,
                    trailing = if (here) MenuTrailing.None else MenuTrailing.Chevron,
                    onClick = if (here) null else ({ switch(workspace.ownerId) }),
                    highlighted = here,
                    modifier = Modifier.testTag(workspaceRowTag(workspace.ownerId)),
                )
                MenuDivider()
            }
        }
        CentreRows(actions, offline)
        MenuRow(
            title = stringResource(R.string.centre_open_title),
            subtitle = if (offline) needs else stringResource(R.string.centre_open_sub),
            icon = MenuIcons.Upload,
            onClick = open,
            enabled = !offline,
            modifier = Modifier.testTag(TAG_PROFILE_OPEN_CENTRE),
        )
    }
}

/**
 * The rows that belong to a centre or to joining one: members and staff
 * inside a centre, and centres' offers.
 *
 * @param actions Where each row leads
 * @param offline Whether the rows wait for a connection
 */
@Composable
private fun CentreRows(actions: MoreActions, offline: Boolean) {
    val needs = stringResource(R.string.more_needs_connection)
    actions.onCentreMembers?.let { members ->
        MenuRow(
            title = stringResource(R.string.centre_members_title),
            subtitle = if (offline) needs else stringResource(R.string.centre_members_sub),
            icon = MenuIcons.Person,
            onClick = members,
            enabled = !offline,
            modifier = Modifier.testTag(TAG_PROFILE_CENTRE_MEMBERS),
        )
        MenuDivider()
    }
    actions.onCentreTimetable?.let { timetable ->
        MenuRow(
            title = stringResource(R.string.timetable_title),
            subtitle = if (offline) needs else stringResource(R.string.timetable_sub),
            icon = MenuIcons.Settings,
            onClick = timetable,
            enabled = !offline,
            modifier = Modifier.testTag(TAG_PROFILE_CENTRE_TIMETABLE),
        )
        MenuDivider()
    }
    actions.onCentreStaff?.let { staff ->
        MenuRow(
            title = stringResource(R.string.staff_title),
            subtitle = if (offline) needs else stringResource(R.string.staff_sub),
            icon = MenuIcons.Person,
            onClick = staff,
            enabled = !offline,
            modifier = Modifier.testTag(TAG_PROFILE_CENTRE_STAFF),
        )
        MenuDivider()
    }
    actions.onCentreOffers?.let { offers ->
        MenuRow(
            title = stringResource(R.string.membership_offers_title),
            subtitle = if (offline) needs else stringResource(R.string.invitations_title),
            icon = MenuIcons.Envelope,
            onClick = offers,
            enabled = !offline,
            modifier = Modifier.testTag(TAG_PROFILE_CENTRE_OFFERS),
        )
        MenuDivider()
    }
}

/**
 * The teacher's GETTING PAID and YOUR RECORDS sections (T9).
 *
 * @param actions Where each row leads
 * @param offline Whether the rows wait for a connection
 */
@Composable
private fun TeacherRows(actions: MoreActions, offline: Boolean) {
    WorkspaceRows(actions, offline)
    actions.onPaymentMethods?.let { open ->
        MenuSection(stringResource(R.string.more_section_getting_paid)) {
            MenuRow(
                title = stringResource(R.string.more_where_students_pay),
                subtitle =
                    stringResource(
                        if (offline) R.string.more_needs_connection else R.string.more_where_students_pay_sub,
                    ),
                icon = MenuIcons.Phone,
                onClick = open,
                enabled = !offline,
                modifier = Modifier.testTag(TAG_PROFILE_PAYMENT_METHODS),
            )
        }
    }
    actions.onCollections?.let { open ->
        MenuSection(stringResource(R.string.more_section_records)) {
            MenuRow(
                title = stringResource(R.string.profile_collections),
                subtitle =
                    stringResource(if (offline) R.string.more_needs_connection else R.string.more_collections_sub),
                icon = MenuIcons.Download,
                onClick = open,
                enabled = !offline,
                modifier = Modifier.testTag(TAG_PROFILE_COLLECTIONS),
            )
            actions.onExpenses?.let { expenses ->
                MenuDivider()
                MenuRow(
                    title = stringResource(R.string.expenses_title),
                    subtitle = stringResource(if (offline) R.string.more_needs_connection else R.string.summary_basis),
                    icon = MenuIcons.Upload,
                    onClick = expenses,
                    enabled = !offline,
                    modifier = Modifier.testTag(TAG_PROFILE_EXPENSES),
                )
            }
            actions.onMoneySummary?.let { summary ->
                MenuDivider()
                MenuRow(
                    title = stringResource(R.string.summary_title),
                    subtitle = stringResource(if (offline) R.string.more_needs_connection else R.string.summary_basis),
                    icon = MenuIcons.Download,
                    onClick = summary,
                    enabled = !offline,
                    modifier = Modifier.testTag(TAG_PROFILE_MONEY_SUMMARY),
                )
            }
            // "2 records not sent yet" (T9): what this phone still holds,
            // which logging out would delete. It informs; nothing to tap.
            if (actions.unsent > 0) {
                MenuDivider()
                MenuRow(
                    title =
                        pluralStringResource(
                            R.plurals.more_unsent_title,
                            actions.unsent,
                            Numerals.count(actions.unsent),
                        ),
                    subtitle = stringResource(R.string.more_unsent_sub),
                    icon = MenuIcons.Upload,
                    trailing = MenuTrailing.None,
                    onClick = null,
                    modifier = Modifier.testTag(TAG_PROFILE_UNSENT),
                )
            }
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
 * Log out works offline; deleting needs the server.
 *
 * @param actions Where each row leads
 * @param offline Whether rows that need the server wait for it
 */
@Composable
private fun AccountRows(actions: MoreActions, offline: Boolean) {
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
            subtitle = stringResource(R.string.more_needs_connection).takeIf { offline },
            icon = MenuIcons.Delete,
            trailing = MenuTrailing.None,
            destructive = true,
            enabled = !offline,
            onClick = actions.onDeleteAccount,
            modifier = Modifier.testTag(TAG_PROFILE_DELETE),
        )
    }
}

/**
 * The APP section: Settings, which this phone keeps and so works offline.
 *
 * @param actions Where each row leads
 */
@Composable
private fun AppRows(actions: MoreActions) {
    val open = actions.onSettings ?: return
    MenuSection(stringResource(R.string.more_section_app)) {
        MenuRow(
            title = stringResource(R.string.more_settings),
            subtitle = stringResource(R.string.more_settings_sub),
            icon = MenuIcons.Settings,
            onClick = open,
            modifier = Modifier.testTag(TAG_PROFILE_SETTINGS),
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
        Lens.CLASS_TEACHER -> R.string.lens_class_teacher
        Lens.STUDENT -> R.string.signup_role_student
        Lens.GUARDIAN -> R.string.signup_role_guardian
    }
