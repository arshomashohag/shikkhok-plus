package com.shikkhokplus.app.feature.hubenquiry.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.LocalTouchScale
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hubenquiry.CONTACT_KIND_PHONE
import com.shikkhokplus.app.feature.hubenquiry.ENQUIRY_MESSAGE_MAX
import com.shikkhokplus.app.feature.hubenquiry.EnquiryForm
import com.shikkhokplus.app.feature.hubenquiry.EnquiryFormUiState
import com.shikkhokplus.app.feature.hubenquiry.EnquiryTarget
import com.shikkhokplus.app.feature.hublisting.ClassLevel
import com.shikkhokplus.app.feature.hublisting.ui.levelLabel

/** The student's name field. */
const val TAG_ENQUIRY_NAME: String = "hub_enquiry_name"

/** The class picker. */
const val TAG_ENQUIRY_LEVEL: String = "hub_enquiry_level"

/** The message field. */
const val TAG_ENQUIRY_MESSAGE: String = "hub_enquiry_message"

/** "Share my phone number with …". */
const val TAG_ENQUIRY_SHARE: String = "hub_enquiry_share"

/** "Don't share it". */
const val TAG_ENQUIRY_NO_SHARE: String = "hub_enquiry_no_share"

/** The adult-guardian declaration. */
const val TAG_ENQUIRY_DECLARE: String = "hub_enquiry_declare"

/** Send request. */
const val TAG_ENQUIRY_SEND: String = "hub_enquiry_send"

/** Retry after a failed send. */
const val TAG_ENQUIRY_RETRY: String = "hub_enquiry_retry"

/** "See my join requests". */
const val TAG_ENQUIRY_MINE: String = "hub_enquiry_mine"

/**
 * Tag for one class in the picker.
 *
 * @param level The class
 * @return The tag
 */
fun enquiryLevelTag(level: ClassLevel): String = "hub_enquiry_level_${level.wire}"

/**
 * What the request form can do.
 *
 * @property onName Changes the student's name
 * @property onLevel Chooses the class
 * @property onMessage Changes the message
 * @property onShare Chooses whether to share the contact
 * @property onDeclare Ticks or unticks the declaration
 * @property onSend Sends the request
 * @property onRetry Sends again after a failure that can be retried
 * @property onRetryLoad Reads the target again
 * @property onMine Opens My join requests
 * @property onBack Leaves the screen
 */
data class EnquiryFormActions(
    val onName: (String) -> Unit = {},
    val onLevel: (ClassLevel) -> Unit = {},
    val onMessage: (String) -> Unit = {},
    val onShare: (Boolean) -> Unit = {},
    val onDeclare: (Boolean) -> Unit = {},
    val onSend: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onRetryLoad: () -> Unit = {},
    val onMine: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * Ask an owner, or one of its batches, to take a student [H5], opened from
 * a public page's "Ask to join" link.
 *
 * **Consent is a choice the guardian makes, never a default.** Sharing the
 * phone (or, for an account with none, the email) is two options with
 * neither chosen, and the adult-guardian declaration is an unticked box;
 * Send stays disabled until a name, a class, the share choice and the
 * declaration are all given. Every refusal is the server's words; a
 * dropped connection keeps what was typed and offers Retry [TC-8].
 *
 * @param state What to render
 * @param actions What the controls do
 * @param modifier Layout modifier from the caller
 */
@Composable
fun EnquiryFormScreen(
    state: EnquiryFormUiState,
    actions: EnquiryFormActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.hub_enquiry_title), modifier = modifier, onBack = actions.onBack) {
        when (state) {
            EnquiryFormUiState.Loading -> SkeletonList(rows = 4)
            EnquiryFormUiState.Invalid -> Banner(title = stringResource(R.string.hub_report_link_invalid))
            is EnquiryFormUiState.Unavailable ->
                Banner(title = stringResource(MessageKeys.resolve(state.messageKey)), tone = BannerTone.INFO)
            is EnquiryFormUiState.Error ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = stringResource(R.string.auth_retry),
                    onRetry = actions.onRetryLoad,
                )
            is EnquiryFormUiState.AlreadyOpen -> {
                TargetCard(state.target)
                Banner(
                    title = stringResource(R.string.hub_enquiry_already_open_title),
                    action = { MineLink(actions.onMine) },
                )
            }
            is EnquiryFormUiState.Sent -> {
                TargetCard(state.target)
                Banner(title = stringResource(R.string.hub_enquiry_sent), action = { MineLink(actions.onMine) })
            }
            is EnquiryFormUiState.Ready -> {
                TargetCard(state.form.target)
                FormFields(state.form, busy = false, actions)
            }
            is EnquiryFormUiState.Sending -> {
                TargetCard(state.form.target)
                FormFields(state.form, busy = true, actions)
            }
        }
    }
}

/** "See my join requests". */
@Composable
private fun MineLink(onMine: () -> Unit) {
    TextAction(stringResource(R.string.hub_enquiry_mine_link), onMine, Modifier.testTag(TAG_ENQUIRY_MINE))
}

/**
 * Who the request goes to: "To {owner}", and the batch when the link named one.
 *
 * @param target The server's target
 */
@Composable
private fun TargetCard(target: EnquiryTarget) {
    ShikkhokCard {
        Text(
            stringResource(R.string.hub_enquiry_to, Numerals.freeText(target.ownerPublicName)),
            style = MaterialTheme.typography.titleMedium,
        )
        target.batchTitle?.let {
            Text(
                Numerals.freeText(it),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * The fields, the failure, and Send.
 *
 * @param form What is shown and typed
 * @param busy Whether the send is in flight
 * @param actions What the controls do
 */
@Composable
private fun FormFields(form: EnquiryForm, busy: Boolean, actions: EnquiryFormActions) {
    ShikkhokTextField(
        value = form.name,
        onValueChange = actions.onName,
        label = stringResource(R.string.hub_enquiry_student_name),
        enabled = !busy,
        fieldModifier = Modifier.testTag(TAG_ENQUIRY_NAME),
    )
    LevelPicker(form.level, enabled = !busy, onPick = actions.onLevel)
    ShikkhokTextField(
        value = form.message,
        onValueChange = actions.onMessage,
        label = stringResource(R.string.hub_enquiry_message),
        help =
            stringResource(
                R.string.hub_report_note_count,
                Numerals.count(form.message.length),
                Numerals.count(ENQUIRY_MESSAGE_MAX),
            ),
        enabled = !busy,
        singleLine = false,
        minLines = 3,
        fieldModifier = Modifier.testTag(TAG_ENQUIRY_MESSAGE),
    )
    ShareChoice(form, busy, actions.onShare)
    CheckRow(
        checked = form.declared,
        label = stringResource(R.string.hub_enquiry_declaration),
        enabled = !busy,
        onChange = actions.onDeclare,
        modifier = Modifier.testTag(TAG_ENQUIRY_DECLARE),
    )
    form.failure?.let { failure ->
        Banner(
            title = stringResource(R.string.hub_enquiry_failed),
            body = stringResource(MessageKeys.resolve(failure.messageKey)),
            tone = BannerTone.ERROR,
            action =
                when {
                    failure.alreadyOpen -> ({ MineLink(actions.onMine) })
                    failure.canRetry -> ({
                        TextAction(
                            stringResource(R.string.auth_retry),
                            actions.onRetry,
                            Modifier.testTag(TAG_ENQUIRY_RETRY),
                            enabled = !busy,
                        )
                    })
                    else -> null
                },
        )
    }
    PrimaryButton(
        text = stringResource(if (busy) R.string.hub_enquiry_sending else R.string.hub_enquiry_send),
        onClick = actions.onSend,
        modifier = Modifier.fillMaxWidth().testTag(TAG_ENQUIRY_SEND),
        enabled = form.canSend && !busy,
    )
}

/**
 * The share choice: two options, neither chosen at first, labelled by what
 * the server says "share" would share, with the help line under them.
 *
 * @param form What is shown
 * @param busy Whether the send is in flight
 * @param onShare Chooses
 */
@Composable
private fun ShareChoice(form: EnquiryForm, busy: Boolean, onShare: (Boolean) -> Unit) {
    val owner = Numerals.freeText(form.target.ownerPublicName)
    val phone = form.target.contactKind == CONTACT_KIND_PHONE
    val label = if (phone) R.string.hub_enquiry_share_phone else R.string.hub_enquiry_share_email
    Text(
        stringResource(R.string.hub_enquiry_share_question),
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.asHeading(),
    )
    Column(Modifier.fillMaxWidth().selectableGroup()) {
        RadioRow(
            selected = form.share == true,
            label = stringResource(label, owner),
            enabled = !busy,
            onClick = { onShare(true) },
            modifier = Modifier.testTag(TAG_ENQUIRY_SHARE),
        )
        RadioRow(
            selected = form.share == false,
            label = stringResource(R.string.hub_enquiry_share_none),
            enabled = !busy,
            onClick = { onShare(false) },
            modifier = Modifier.testTag(TAG_ENQUIRY_NO_SHARE),
        )
    }
    Text(
        stringResource(R.string.hub_enquiry_share_help),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/** One option of a pick-one group, the whole row its touch target. */
@Composable
private fun RadioRow(
    selected: Boolean,
    label: String,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier
            .fillMaxWidth()
            .heightIn(min = LocalTouchScale.current.rowSingle)
            .selectable(selected = selected, enabled = enabled, role = Role.RadioButton, onClick = onClick)
            .padding(horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = null, enabled = enabled)
        Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(start = 12.dp).weight(1f))
    }
}

/** A box with its label, the whole row its touch target. */
@Composable
private fun CheckRow(
    checked: Boolean,
    label: String,
    enabled: Boolean,
    onChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier
            .fillMaxWidth()
            .heightIn(min = LocalTouchScale.current.rowSingle)
            .toggleable(value = checked, enabled = enabled, role = Role.Checkbox, onValueChange = onChange)
            .padding(horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = null, enabled = enabled)
        Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(start = 12.dp).weight(1f))
    }
}

/**
 * The class picker, offering the hub's closed list in the listing editor's words.
 *
 * @param level The chosen class, or null
 * @param enabled Whether it can be changed
 * @param onPick Chooses
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LevelPicker(level: ClassLevel?, enabled: Boolean, onPick: (ClassLevel) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded && enabled, onExpandedChange = { expanded = it && enabled }) {
        OutlinedTextField(
            value = level?.let { stringResource(levelLabel(it)) }.orEmpty(),
            onValueChange = {},
            readOnly = true,
            enabled = enabled,
            label = { Text(stringResource(R.string.hub_enquiry_class_level)) },
            placeholder = { Text(stringResource(R.string.hub_enquiry_class_choose)) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier =
                Modifier
                    .fillMaxWidth()
                    .menuAnchor(MenuAnchorType.PrimaryNotEditable)
                    .testTag(TAG_ENQUIRY_LEVEL),
        )
        ExposedDropdownMenu(expanded = expanded && enabled, onDismissRequest = { expanded = false }) {
            ClassLevel.entries.forEach { option ->
                DropdownMenuItem(
                    text = { Text(stringResource(levelLabel(option)), color = MaterialTheme.colorScheme.onSurface) },
                    onClick = {
                        onPick(option)
                        expanded = false
                    },
                    modifier = Modifier.testTag(enquiryLevelTag(option)),
                )
            }
        }
    }
}
