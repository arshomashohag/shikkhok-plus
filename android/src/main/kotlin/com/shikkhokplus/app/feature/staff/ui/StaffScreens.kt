package com.shikkhokplus.app.feature.staff.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
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
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.isoDate
import com.shikkhokplus.app.core.format.isoToUtcMillis
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.format.todayAsUtcMillis
import com.shikkhokplus.app.core.network.StaffDto
import com.shikkhokplus.app.core.ui.AddressFields
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.staff.PayBasis
import com.shikkhokplus.app.feature.staff.StaffFormMode
import com.shikkhokplus.app.feature.staff.StaffFormUiState
import com.shikkhokplus.app.feature.staff.StaffListUiState

/** The invite-a-teacher action. */
const val TAG_STAFF_INVITE: String = "staff_invite"

/** The add-other-staff action. */
const val TAG_STAFF_ADD_OTHER: String = "staff_add_other"

/** The empty console. */
const val TAG_STAFF_EMPTY: String = "staff_empty"

/** The confirm button of the mark-as-left dialog. */
const val TAG_STAFF_LEAVE_CONFIRM: String = "staff_leave_confirm"

/** The staff form's name field. */
const val TAG_STAFF_NAME: String = "staff_name"

/** The staff form's phone field. */
const val TAG_STAFF_PHONE: String = "staff_phone"

/** The staff form's amount field. */
const val TAG_STAFF_RATE: String = "staff_rate"

/** The staff form's save button. */
const val TAG_STAFF_SAVE: String = "staff_save"

/**
 * Tag for one record.
 *
 * @param staffId The record
 * @return The tag
 */
fun staffRowTag(staffId: String): String = "staff_row_$staffId"

/**
 * Tag for one record's mark-as-left action.
 *
 * @param staffId The record
 * @return The tag
 */
fun staffLeaveTag(staffId: String): String = "staff_leave_$staffId"

/**
 * Tag for one pay-basis chip.
 *
 * @param basis The basis
 * @return The tag
 */
fun payBasisTag(basis: PayBasis): String = "staff_basis_${basis.wire}"

/**
 * The line saying how someone is paid, from the server's basis and rate.
 *
 * @param row The record
 * @return The line
 */
@Composable
fun payLine(row: StaffDto): String {
    val rate = row.payRate
    return when (PayBasis.fromWire(row.payBasis)) {
        PayBasis.MONTHLY -> rate?.let { stringResource(R.string.staff_pay_monthly, Numerals.money(it)) }
        PayBasis.PER_CLASS -> rate?.let { stringResource(R.string.staff_pay_per_class, Numerals.money(it)) }
        PayBasis.NONE -> null
    } ?: stringResource(R.string.staff_pay_none)
}

private fun kindLabel(row: StaffDto): Int =
    if (row.isTeacher) R.string.staff_kind_teacher else R.string.staff_kind_other

private fun accessLabel(access: String): Int =
    when (access) {
        "invited" -> R.string.staff_access_invited
        "declined" -> R.string.staff_access_declined
        "active" -> R.string.staff_access_active
        "revoked" -> R.string.staff_access_revoked
        else -> R.string.staff_access_none
    }

/**
 * What the console's controls call.
 *
 * @property onInviteTeacher Opens the invite-a-teacher form
 * @property onAddOther Opens the add-other-staff form
 * @property onEdit Opens one record's editor
 * @property onLeave Marks one record as left, once confirmed
 * @property onRetry Reads the list again
 * @property onBack Leaves the screen
 */
data class StaffListActions(
    val onInviteTeacher: () -> Unit = {},
    val onAddOther: () -> Unit = {},
    val onEdit: (String) -> Unit = {},
    val onLeave: (String) -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * Teachers & staff: who works at the centre, their pay terms and whether
 * they use the app, with inviting a teacher, adding other staff,
 * correcting a record and marking someone as left.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun StaffListScreen(
    state: StaffListUiState,
    actions: StaffListActions,
    modifier: Modifier = Modifier,
) {
    var leaving by remember { mutableStateOf<StaffDto?>(null) }
    ScreenScaffold(
        title = stringResource(R.string.staff_title),
        subtitle = stringResource(R.string.staff_sub),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        when (state) {
            StaffListUiState.Loading -> SkeletonList(rows = 4)
            is StaffListUiState.Loaded -> {
                state.notice?.let {
                    Banner(
                        title = stringResource(R.string.staff_marked_left, Numerals.freeText(it)),
                        tone = BannerTone.INFO,
                    )
                }
                state.failureKey?.let {
                    Banner(title = stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR)
                }
                if (state.staff.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.staff_title),
                        body = stringResource(R.string.staff_empty),
                        modifier = Modifier.testTag(TAG_STAFF_EMPTY),
                    )
                }
                state.staff.forEach { row ->
                    StaffCard(row, onEdit = { actions.onEdit(row.staffId) }, onLeave = { leaving = row })
                }
            }
            is StaffListUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
        }
        if (state !is StaffListUiState.Loading) {
            PrimaryButton(
                text = stringResource(R.string.staff_invite_teacher),
                onClick = actions.onInviteTeacher,
                modifier = Modifier.fillMaxWidth().testTag(TAG_STAFF_INVITE),
            )
            SecondaryButton(
                text = stringResource(R.string.staff_add_other),
                onClick = actions.onAddOther,
                modifier = Modifier.fillMaxWidth().testTag(TAG_STAFF_ADD_OTHER),
            )
        }
    }
    leaving?.let { row ->
        AlertDialog(
            onDismissRequest = { leaving = null },
            title = { Text(stringResource(R.string.staff_leave)) },
            text = { Text(stringResource(R.string.staff_leave_confirm, Numerals.freeText(row.displayName))) },
            confirmButton = {
                TextAction(
                    text = stringResource(R.string.staff_leave),
                    onClick = {
                        leaving = null
                        actions.onLeave(row.staffId)
                    },
                    modifier = Modifier.testTag(TAG_STAFF_LEAVE_CONFIRM),
                )
            },
            dismissButton = { TextAction(stringResource(R.string.action_cancel), { leaving = null }) },
        )
    }
}

@Composable
private fun StaffCard(row: StaffDto, onEdit: () -> Unit, onLeave: () -> Unit) {
    ShikkhokCard(modifier = Modifier.testTag(staffRowTag(row.staffId)), onClick = onEdit) {
        Text(Numerals.freeText(row.displayName), style = MaterialTheme.typography.titleMedium)
        Text(
            text =
                listOfNotNull(
                    row.roleLabel?.let(Numerals::freeText) ?: stringResource(kindLabel(row)),
                    payLine(row),
                ).joinToString(" · "),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text =
                row.leftOn?.let { stringResource(R.string.staff_status_left, shortDate(it)) }
                    ?: stringResource(accessLabel(row.access)),
            style = MaterialTheme.typography.labelLarge,
        )
        if (!row.hasLeft) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextAction(text = stringResource(R.string.staff_edit), onClick = onEdit)
                TextAction(
                    text = stringResource(R.string.staff_leave),
                    onClick = onLeave,
                    modifier = Modifier.testTag(staffLeaveTag(row.staffId)),
                )
            }
        }
    }
}

/**
 * What the staff form's controls call.
 *
 * @property onName Edits the name
 * @property onPhone Edits the phone
 * @property onEmail Edits the email
 * @property onRoleLabel Edits what they do
 * @property onAddress Edits the address
 * @property onBasis Chooses how they are paid
 * @property onRate Edits the amount
 * @property onJoinedOn Picks the joining date
 * @property onSave Sends the form
 * @property onCancel Leaves without saving
 */
data class StaffFormActions(
    val onName: (String) -> Unit = {},
    val onPhone: (String) -> Unit = {},
    val onEmail: (String) -> Unit = {},
    val onRoleLabel: (String) -> Unit = {},
    val onAddress: (com.shikkhokplus.app.core.model.PostalAddress) -> Unit = {},
    val onBasis: (PayBasis) -> Unit = {},
    val onRate: (String) -> Unit = {},
    val onJoinedOn: (String) -> Unit = {},
    val onSave: () -> Unit = {},
    val onCancel: () -> Unit = {},
)

/**
 * Invite a teacher, add other staff, or correct a record: name, contact,
 * what they do, address, pay terms and joining date. A teacher's number
 * is fixed once invited, because the invitation went to it.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
fun StaffFormScreen(
    state: StaffFormUiState,
    actions: StaffFormActions,
    modifier: Modifier = Modifier,
) {
    var picking by remember { mutableStateOf(false) }
    val title =
        when (state.mode) {
            StaffFormMode.InviteTeacher -> R.string.staff_invite_teacher
            StaffFormMode.AddOther -> R.string.staff_add_other
            is StaffFormMode.Edit -> R.string.staff_edit
        }
    ScreenScaffold(title = stringResource(title), modifier = modifier, onBack = actions.onCancel) {
        if (state.mode == StaffFormMode.InviteTeacher) {
            Text(
                stringResource(R.string.staff_invite_help),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        ShikkhokTextField(
            value = state.name,
            onValueChange = actions.onName,
            label = stringResource(R.string.staff_name_label),
            fieldModifier = Modifier.testTag(TAG_STAFF_NAME),
        )
        ShikkhokTextField(
            value = state.phone,
            onValueChange = actions.onPhone,
            label = stringResource(R.string.staff_phone_label),
            enabled = state.mode !is StaffFormMode.Edit,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            fieldModifier = Modifier.testTag(TAG_STAFF_PHONE),
        )
        ShikkhokTextField(
            value = state.email,
            onValueChange = actions.onEmail,
            label = stringResource(R.string.staff_email_label),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
        )
        if (state.isOther) {
            ShikkhokTextField(
                value = state.roleLabel,
                onValueChange = actions.onRoleLabel,
                label = stringResource(R.string.staff_role_label),
            )
        }
        PaySection(state, actions)
        Text(stringResource(R.string.staff_joined_label), style = MaterialTheme.typography.labelLarge)
        SecondaryButton(
            text = shortDate(state.joinedOn.ifBlank { isoDate(todayAsUtcMillis()) }),
            onClick = { picking = true },
            modifier = Modifier.fillMaxWidth(),
        )
        Text(stringResource(R.string.staff_address_heading), style = MaterialTheme.typography.labelLarge)
        AddressFields(address = state.address, onChange = actions.onAddress)
        state.failureKey?.let { Banner(title = stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR) }
        PrimaryButton(
            text = stringResource(saveLabel(state.mode)),
            onClick = actions.onSave,
            enabled = state.canSave,
            modifier = Modifier.fillMaxWidth().testTag(TAG_STAFF_SAVE),
        )
        SecondaryButton(
            text = stringResource(R.string.action_cancel),
            onClick = actions.onCancel,
            modifier = Modifier.fillMaxWidth(),
        )
    }
    if (picking) {
        val picker =
            rememberDatePickerState(
                initialSelectedDateMillis = isoToUtcMillis(state.joinedOn) ?: todayAsUtcMillis(),
            )
        DatePickerDialog(
            onDismissRequest = { picking = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        picker.selectedDateMillis?.let { actions.onJoinedOn(isoDate(it)) }
                        picking = false
                    },
                ) { Text(stringResource(R.string.action_ok)) }
            },
            dismissButton = {
                TextButton(onClick = { picking = false }) { Text(stringResource(R.string.action_cancel)) }
            },
        ) { DatePicker(state = picker) }
    }
}

private fun saveLabel(mode: StaffFormMode): Int =
    if (mode == StaffFormMode.InviteTeacher) R.string.staff_invite_teacher else R.string.staff_save

/**
 * How they are paid, and the amount with a paid basis.
 *
 * @param state The form
 * @param actions What the controls call
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PaySection(state: StaffFormUiState, actions: StaffFormActions) {
    Text(stringResource(R.string.staff_pay_basis_label), style = MaterialTheme.typography.labelLarge)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        PayBasis.entries.forEach { basis ->
            FilterChip(
                selected = state.basis == basis,
                onClick = { actions.onBasis(basis) },
                label = { Text(stringResource(basisLabel(basis))) },
                modifier = Modifier.testTag(payBasisTag(basis)),
            )
        }
    }
    if (state.basis != PayBasis.NONE) {
        ShikkhokTextField(
            value = state.typedRate,
            onValueChange = actions.onRate,
            label = stringResource(R.string.staff_pay_rate_label),
            prefix = "৳",
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            fieldModifier = Modifier.testTag(TAG_STAFF_RATE),
        )
    }
}

private fun basisLabel(basis: PayBasis): Int =
    when (basis) {
        PayBasis.MONTHLY -> R.string.staff_pay_basis_monthly
        PayBasis.PER_CLASS -> R.string.staff_pay_basis_per_class
        PayBasis.NONE -> R.string.staff_pay_basis_none
    }

