package com.shikkhokplus.app.feature.centres.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.centres.MemberRole
import com.shikkhokplus.app.feature.centres.MembersBody
import com.shikkhokplus.app.feature.centres.MembersUiState
import com.shikkhokplus.app.feature.centres.OffersUiState
import com.shikkhokplus.app.feature.centres.OpenCentreUiState

/** The open-a-centre form's centre name. */
const val TAG_CENTRE_NAME: String = "centre_name"

/** The open-a-centre form's submit button. */
const val TAG_CENTRE_OPEN: String = "centre_open"

/** The invite form's submit button. */
const val TAG_INVITE_SUBMIT: String = "centre_invite_submit"

/** The invite form's name field. */
const val TAG_INVITE_NAME: String = "centre_invite_name"

/** The invite form's phone field. */
const val TAG_INVITE_PHONE: String = "centre_invite_phone"

/** The confirm button of the remove dialog. */
const val TAG_MEMBER_REMOVE_CONFIRM: String = "centre_member_remove_confirm"

/** The centres' offers section. */
const val TAG_OFFERS: String = "centre_offers"

/**
 * Tag for one member's remove action.
 *
 * @param memberId The membership
 * @return The tag
 */
fun memberRemoveTag(memberId: String): String = "centre_member_remove_$memberId"

/**
 * Tag for one offer's accept action.
 *
 * @param memberId The membership
 * @return The tag
 */
fun offerAcceptTag(memberId: String): String = "centre_offer_accept_$memberId"

/**
 * Tag for one offer's decline action.
 *
 * @param memberId The membership
 * @return The tag
 */
fun offerDeclineTag(memberId: String): String = "centre_offer_decline_$memberId"

/**
 * The label for a member's role.
 *
 * @param role The role
 * @return Its string resource
 */
fun roleLabel(role: MemberRole): Int =
    if (role == MemberRole.MANAGER) R.string.centre_member_role_manager else R.string.centre_member_role_teacher

/**
 * Open a coaching centre: its name and the opener's name. The opener
 * becomes its first manager and the app moves into it.
 *
 * @param state What to render
 * @param onName Edits the centre's name
 * @param onManagerName Edits the opener's name
 * @param onOpen Opens the centre
 * @param onCancel Leaves without opening
 * @param modifier Layout modifier from the caller
 */
@Composable
fun OpenCentreScreen(
    state: OpenCentreUiState,
    onName: (String) -> Unit,
    onManagerName: (String) -> Unit,
    onOpen: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.centre_open_title), modifier = modifier, onBack = onCancel) {
        Text(
            stringResource(R.string.centre_open_sub),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        ShikkhokTextField(
            value = state.name,
            onValueChange = onName,
            label = stringResource(R.string.centre_name_label),
            fieldModifier = Modifier.testTag(TAG_CENTRE_NAME),
        )
        ShikkhokTextField(
            value = state.managerName,
            onValueChange = onManagerName,
            label = stringResource(R.string.centre_manager_name_label),
        )
        state.failureKey?.let { Banner(title = stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR) }
        PrimaryButton(
            text = stringResource(R.string.centre_open_submit),
            onClick = onOpen,
            enabled = state.canOpen,
            modifier = Modifier.fillMaxWidth().testTag(TAG_CENTRE_OPEN),
        )
        SecondaryButton(
            text = stringResource(R.string.action_cancel),
            onClick = onCancel,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/**
 * What the members screen's controls call.
 *
 * @property onInviteName Edits the invitee's name
 * @property onInvitePhone Edits the invitee's phone
 * @property onInviteRole Chooses the invitee's role
 * @property onInvite Sends the invitation
 * @property onRemove Removes a member, once confirmed
 * @property onRetry Reads the list again
 * @property onBack Leaves the screen
 */
data class MembersActions(
    val onInviteName: (String) -> Unit = {},
    val onInvitePhone: (String) -> Unit = {},
    val onInviteRole: (MemberRole) -> Unit = {},
    val onInvite: () -> Unit = {},
    val onRemove: (String) -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * A centre's members, for its managers: who is invited, who accepted or
 * declined, inviting by phone, and removing someone. The server refuses
 * removing the last manager.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MembersScreen(
    state: MembersUiState,
    actions: MembersActions,
    modifier: Modifier = Modifier,
) {
    var removing by remember { mutableStateOf<MemberDto?>(null) }
    ScreenScaffold(
        title = stringResource(R.string.centre_members_title),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        state.failureKey?.let { Banner(title = stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR) }
        state.invited?.let {
            Banner(title = stringResource(R.string.centre_invite_sent, Numerals.freeText(it)), tone = BannerTone.INFO)
        }
        when (val body = state.body) {
            MembersBody.Loading -> SkeletonList(rows = 3)
            is MembersBody.Loaded ->
                if (body.members.none { !it.isYou && !it.revoked }) {
                    EmptyState(
                        title = stringResource(R.string.centre_members_title),
                        body = stringResource(R.string.centre_members_empty),
                    )
                    body.members.filter { it.isYou }.forEach { MemberCard(it) { removing = it } }
                } else {
                    body.members.forEach { member -> MemberCard(member) { removing = member } }
                }
            is MembersBody.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = null,
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) actions.onRetry else null,
                )
        }
        Text(
            stringResource(R.string.centre_invite_title),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.asHeading(),
        )
        Text(
            stringResource(R.string.centre_invite_help),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        ShikkhokTextField(
            value = state.inviteName,
            onValueChange = actions.onInviteName,
            label = stringResource(R.string.centre_invite_name_label),
            fieldModifier = Modifier.testTag(TAG_INVITE_NAME),
        )
        ShikkhokTextField(
            value = state.invitePhone,
            onValueChange = actions.onInvitePhone,
            label = stringResource(R.string.centre_invite_phone_label),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            fieldModifier = Modifier.testTag(TAG_INVITE_PHONE),
        )
        Text(stringResource(R.string.centre_invite_role_label), style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MemberRole.entries.forEach { role ->
                FilterChip(
                    selected = state.inviteRole == role,
                    onClick = { actions.onInviteRole(role) },
                    label = { Text(stringResource(roleLabel(role))) },
                )
            }
        }
        PrimaryButton(
            text = stringResource(R.string.centre_invite_submit),
            onClick = actions.onInvite,
            enabled = state.canInvite,
            modifier = Modifier.fillMaxWidth().testTag(TAG_INVITE_SUBMIT),
        )
    }
    removing?.let { member ->
        AlertDialog(
            onDismissRequest = { removing = null },
            title = { Text(stringResource(R.string.centre_member_remove)) },
            text = {
                Text(stringResource(R.string.centre_member_remove_confirm, Numerals.freeText(member.displayName)))
            },
            confirmButton = {
                TextAction(
                    text = stringResource(R.string.centre_member_remove),
                    onClick = {
                        removing = null
                        actions.onRemove(member.memberId)
                    },
                    modifier = Modifier.testTag(TAG_MEMBER_REMOVE_CONFIRM),
                )
            },
            dismissButton = { TextAction(stringResource(R.string.action_cancel), { removing = null }) },
        )
    }
}

@Composable
private fun MemberCard(member: MemberDto, onRemove: () -> Unit) {
    ShikkhokCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(Numerals.freeText(member.displayName), style = MaterialTheme.typography.titleMedium)
                Text(
                    text =
                        listOf(
                            stringResource(roleLabel(MemberRole.fromWire(member.role))),
                            Numerals.phone(member.phone),
                            stringResource(statusLabel(member)),
                        ).joinToString(" · "),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (!member.revoked && !member.isYou) {
                TextAction(
                    text = stringResource(R.string.centre_member_remove),
                    onClick = onRemove,
                    modifier = Modifier.testTag(memberRemoveTag(member.memberId)),
                )
            }
        }
    }
}

private fun statusLabel(member: MemberDto): Int =
    when {
        member.isYou -> R.string.centre_member_you
        member.revoked -> R.string.centre_member_revoked
        member.decision == "accepted" -> R.string.centre_member_accepted
        member.decision == "declined" -> R.string.centre_member_declined
        else -> R.string.centre_member_pending
    }

/**
 * The centres' offers to the signed-in account, each to accept or
 * decline. Draws nothing when there are none.
 *
 * @param state The offers
 * @param onAccept Accepts one
 * @param onDecline Declines one
 */
@Composable
fun CentreOffersSection(
    state: OffersUiState,
    onAccept: (String) -> Unit,
    onDecline: (String) -> Unit,
) {
    if (state.offers.isEmpty() && state.failureKey == null) return
    Column(Modifier.fillMaxWidth().testTag(TAG_OFFERS), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            stringResource(R.string.membership_offers_title),
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.asHeading(),
        )
        state.failureKey?.let { Banner(title = stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR) }
        state.offers.forEach { offer ->
            ShikkhokCard {
                Text(Numerals.freeText(offer.centreName), style = MaterialTheme.typography.titleMedium)
                Text(
                    stringResource(
                        R.string.membership_offer_line,
                        stringResource(roleLabel(MemberRole.fromWire(offer.role))),
                    ),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End)) {
                    TextAction(
                        text = stringResource(R.string.invitation_decline),
                        onClick = { onDecline(offer.memberId) },
                        enabled = state.busy == null,
                        modifier = Modifier.testTag(offerDeclineTag(offer.memberId)),
                    )
                    TextAction(
                        text = stringResource(R.string.invitation_accept),
                        onClick = { onAccept(offer.memberId) },
                        enabled = state.busy == null,
                        modifier = Modifier.testTag(offerAcceptTag(offer.memberId)),
                    )
                }
            }
        }
    }
}

/**
 * The centres' offers as a screen of their own, opened from a teacher's
 * More; students and guardians see the same section on Invitations.
 *
 * @param state The offers
 * @param onAccept Accepts one
 * @param onDecline Declines one
 * @param onBack Leaves the screen
 * @param modifier Layout modifier from the caller
 */
@Composable
fun CentreOffersScreen(
    state: OffersUiState,
    onAccept: (String) -> Unit,
    onDecline: (String) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.membership_offers_title), modifier = modifier, onBack = onBack) {
        if (state.offers.isEmpty() && state.failureKey == null) {
            Text(stringResource(R.string.invitations_empty_title), style = MaterialTheme.typography.bodyLarge)
        }
        CentreOffersSection(state, onAccept, onDecline)
    }
}
