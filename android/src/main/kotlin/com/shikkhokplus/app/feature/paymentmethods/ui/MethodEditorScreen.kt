package com.shikkhokplus.app.feature.paymentmethods.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.PhoneField
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.paymentmethods.MethodEditorState
import com.shikkhokplus.app.feature.paymentmethods.MethodEditorStatus
import com.shikkhokplus.app.feature.paymentmethods.MethodEditorViewModel
import com.shikkhokplus.app.feature.paymentmethods.MethodKind
import com.shikkhokplus.app.feature.paymentmethods.ProviderOption

/** The mobile-banking kind chip. */
const val TAG_EDITOR_KIND_MOBILE: String = "editor_kind_mobile"

/** The bank kind chip. */
const val TAG_EDITOR_KIND_BANK: String = "editor_kind_bank"

/** The editable service or bank-name field. */
const val TAG_EDITOR_PROVIDER: String = "editor_provider"

/** The mobile number field. */
const val TAG_EDITOR_MOBILE: String = "editor_mobile"

/** The bank account number field. */
const val TAG_EDITOR_ACCOUNT_NUMBER: String = "editor_account_number"

/** The account holder field. */
const val TAG_EDITOR_ACCOUNT_NAME: String = "editor_account_name"

/** The branch field. */
const val TAG_EDITOR_BRANCH: String = "editor_branch"

/** The note field. */
const val TAG_EDITOR_NOTE: String = "editor_note"

/** The save control. */
const val TAG_EDITOR_SAVE: String = "editor_save"

/** The retry control after a failed save. */
const val TAG_EDITOR_RETRY: String = "editor_retry"

/**
 * Wires the editor to its ViewModel and leaves when the save lands.
 *
 * @param model The form's ViewModel
 * @param onDone Called once the server has stored the method
 * @param onBack Called to leave without saving
 */
@Composable
fun MethodEditorRoute(
    model: MethodEditorViewModel,
    onDone: () -> Unit,
    onBack: () -> Unit = onDone,
) {
    val state by model.state.collectAsState()
    LaunchedEffect(state.status) {
        if (state.status == MethodEditorStatus.Saved) onDone()
    }
    MethodEditorScreen(
        state = state,
        options = model.providerOptions(),
        onKind = model::selectKind,
        onProvider = model::setProvider,
        onMobile = model::setMobileNumber,
        onAccountNumber = model::setAccountNumber,
        onAccountName = model::setAccountName,
        onBranch = model::setBranchName,
        onNote = model::setNote,
        onSave = model::save,
        onRetry = model::retry,
        onBack = onBack,
    )
}

/**
 * P2 and P3, adding or editing one method.
 *
 * @param state What to render
 * @param options The dropdown's entries for the text typed so far
 * @param onKind Called to switch between mobile and bank
 * @param onProvider Called with the service or bank name
 * @param onMobile Called with the number
 * @param onAccountNumber Called with the account number
 * @param onAccountName Called with the account holder
 * @param onBranch Called with the branch
 * @param onNote Called with the note
 * @param onSave Called to send the form
 * @param onRetry Called to send it again after a failure
 * @param onBack Called to leave the screen
 * @param modifier Layout modifier from the caller
 */
@Composable
fun MethodEditorScreen(
    state: MethodEditorState,
    options: List<ProviderOption>,
    onKind: (MethodKind) -> Unit,
    onProvider: (String) -> Unit,
    onMobile: (String) -> Unit,
    onAccountNumber: (String) -> Unit,
    onAccountName: (String) -> Unit,
    onBranch: (String) -> Unit,
    onNote: (String) -> Unit,
    onSave: () -> Unit,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title =
            stringResource(
                if (state.isEditing) R.string.method_editor_title_edit else R.string.method_editor_title_add,
            ),
        modifier = modifier,
        onBack = onBack,
    ) {
        if (state.status == MethodEditorStatus.Saving) {
            LogoLoader(label = stringResource(R.string.method_saving))
            return@ScreenScaffold
        }
        if (!state.isEditing) {
            Row(horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
                FilterChip(
                    selected = state.kind == MethodKind.MOBILE,
                    onClick = { onKind(MethodKind.MOBILE) },
                    label = { Text(stringResource(R.string.method_kind_mobile)) },
                    modifier = Modifier.testTag(TAG_EDITOR_KIND_MOBILE),
                )
                FilterChip(
                    selected = state.kind == MethodKind.BANK,
                    onClick = { onKind(MethodKind.BANK) },
                    label = { Text(stringResource(R.string.method_kind_bank)) },
                    modifier = Modifier.testTag(TAG_EDITOR_KIND_BANK),
                )
            }
        }
        when (state.kind) {
            MethodKind.MOBILE -> {
                ProviderDropdown(
                    label = stringResource(R.string.method_service_label),
                    help = stringResource(R.string.method_service_help),
                    value = state.provider,
                    options = options,
                    onValue = onProvider,
                )
                PhoneField(
                    value = state.mobileNumber,
                    onValueChange = onMobile,
                    label = stringResource(R.string.method_number_label),
                    fieldModifier = Modifier.testTag(TAG_EDITOR_MOBILE),
                )
            }

            MethodKind.BANK -> {
                ShikkhokTextField(
                    value = state.accountNumber,
                    onValueChange = onAccountNumber,
                    label = stringResource(R.string.method_account_number_label),
                    fieldModifier = Modifier.testTag(TAG_EDITOR_ACCOUNT_NUMBER),
                )
                ShikkhokTextField(
                    value = state.accountName,
                    onValueChange = onAccountName,
                    label = stringResource(R.string.method_account_name_label),
                    fieldModifier = Modifier.testTag(TAG_EDITOR_ACCOUNT_NAME),
                )
                ProviderDropdown(
                    label = stringResource(R.string.method_bank_name_label),
                    help = stringResource(R.string.method_bank_help),
                    value = state.provider,
                    options = options,
                    onValue = onProvider,
                )
                ShikkhokTextField(
                    value = state.branchName,
                    onValueChange = onBranch,
                    label = stringResource(R.string.method_branch_label),
                    fieldModifier = Modifier.testTag(TAG_EDITOR_BRANCH),
                )
            }
        }
        ShikkhokTextField(
            value = state.note,
            onValueChange = onNote,
            label = stringResource(R.string.method_note_label),
            fieldModifier = Modifier.testTag(TAG_EDITOR_NOTE),
        )
        (state.status as? MethodEditorStatus.Failed)?.let { failed ->
            Banner(
                title = stringResource(MessageKeys.resolve(failed.messageKey)),
                tone = BannerTone.ERROR,
            )
            if (failed.retryable) {
                PrimaryButton(
                    text = stringResource(R.string.auth_retry),
                    onClick = onRetry,
                    modifier = Modifier.fillMaxWidth().testTag(TAG_EDITOR_RETRY),
                )
            }
        }
        PrimaryButton(
            text = stringResource(R.string.method_save),
            onClick = onSave,
            enabled = state.canSave,
            modifier = Modifier.fillMaxWidth().testTag(TAG_EDITOR_SAVE),
        )
    }
}

/**
 * A text field that doubles as a dropdown of suggestions.
 *
 * Typing filters the suggestions and offers "Use “X”"; picking either
 * puts that text in the field.
 *
 * @param label The label above the field
 * @param help The line under the field
 * @param value The text typed so far
 * @param options The entries to show
 * @param onValue Called with the new text
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ProviderDropdown(
    label: String,
    help: String,
    value: String,
    options: List<ProviderOption>,
    onValue: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded && options.isNotEmpty(), onExpandedChange = { expanded = it }) {
        OutlinedTextField(
            value = value,
            onValueChange = {
                onValue(it)
                expanded = true
            },
            label = { Text(label) },
            supportingText = { Text(help) },
            singleLine = true,
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier =
                Modifier
                    .fillMaxWidth()
                    .menuAnchor(MenuAnchorType.PrimaryEditable)
                    .testTag(TAG_EDITOR_PROVIDER),
        )
        ExposedDropdownMenu(expanded = expanded && options.isNotEmpty(), onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                val text =
                    when (option) {
                        is ProviderOption.Service -> option.name
                        is ProviderOption.UseTyped -> stringResource(R.string.method_service_use, option.text)
                    }
                val picked =
                    when (option) {
                        is ProviderOption.Service -> option.name
                        is ProviderOption.UseTyped -> option.text
                    }
                DropdownMenuItem(
                    text = { Text(text, color = MaterialTheme.colorScheme.onSurface) },
                    onClick = {
                        onValue(picked)
                        expanded = false
                    },
                )
            }
        }
    }
}
