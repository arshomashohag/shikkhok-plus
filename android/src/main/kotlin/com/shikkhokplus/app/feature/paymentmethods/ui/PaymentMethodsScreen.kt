package com.shikkhokplus.app.feature.paymentmethods.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
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
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.paymentmethods.MethodKind
import com.shikkhokplus.app.feature.paymentmethods.MethodRow
import com.shikkhokplus.app.feature.paymentmethods.PaymentMethodsUiState

/** The add-mobile-banking action. */
const val TAG_METHODS_ADD_MOBILE: String = "methods_add_mobile"

/** The add-bank-account action. */
const val TAG_METHODS_ADD_BANK: String = "methods_add_bank"

/** The retry control on a failed read. */
const val TAG_METHODS_RETRY: String = "methods_retry"

/** The empty state. */
const val TAG_METHODS_EMPTY: String = "methods_empty"

/** The confirm button in the removal dialog. */
const val TAG_METHODS_REMOVE_CONFIRM: String = "methods_remove_confirm"

/**
 * Tag for one method row.
 *
 * @param methodId The method
 * @return The tag
 */
fun methodRowTag(methodId: String): String = "method_row_$methodId"

/**
 * Tag for one row's remove action.
 *
 * @param methodId The method
 * @return The tag
 */
fun methodRemoveTag(methodId: String): String = "method_remove_$methodId"

/**
 * P1, the teacher's payment methods.
 *
 * @param state What to render
 * @param onAddMobile Called to add a mobile banking number
 * @param onAddBank Called to add a bank account
 * @param onEdit Called with the method to edit
 * @param onRemove Called with the method to retire, once confirmed
 * @param onRetry Called when a failed read offers a retry
 * @param onBack Called to leave the screen
 * @param modifier Layout modifier from the caller
 */
@Composable
fun PaymentMethodsScreen(
    state: PaymentMethodsUiState,
    onAddMobile: () -> Unit,
    onAddBank: () -> Unit,
    onEdit: (String) -> Unit,
    onRemove: (String) -> Unit,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var removing by remember { mutableStateOf<String?>(null) }

    ScreenScaffold(
        title = stringResource(R.string.payment_methods_title),
        modifier = modifier,
        onBack = onBack,
    ) {
        Text(
            text = stringResource(R.string.payment_methods_intro),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        when (state) {
            PaymentMethodsUiState.Loading -> SkeletonList(rows = 3)

            PaymentMethodsUiState.Empty ->
                EmptyState(
                    title = stringResource(R.string.payment_methods_empty_title),
                    body = stringResource(R.string.payment_methods_empty_body),
                    modifier = Modifier.testTag(TAG_METHODS_EMPTY),
                )

            is PaymentMethodsUiState.Loaded -> {
                state.removeFailedKey?.let {
                    Banner(
                        title = stringResource(MessageKeys.resolve(it)),
                        tone = BannerTone.ERROR,
                    )
                }
                state.rows.forEach { row ->
                    MethodCard(
                        row = row,
                        onEdit = { onEdit(row.methodId) },
                        onRemove = { removing = row.methodId },
                    )
                }
            }

            is PaymentMethodsUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) onRetry else null,
                )
        }
        if (state != PaymentMethodsUiState.Loading) {
            SecondaryButton(
                text = stringResource(R.string.payment_methods_add_mobile),
                onClick = onAddMobile,
                modifier = Modifier.fillMaxWidth().testTag(TAG_METHODS_ADD_MOBILE),
            )
            SecondaryButton(
                text = stringResource(R.string.payment_methods_add_bank),
                onClick = onAddBank,
                modifier = Modifier.fillMaxWidth().testTag(TAG_METHODS_ADD_BANK),
            )
        }
    }

    removing?.let { id ->
        AlertDialog(
            onDismissRequest = { removing = null },
            title = { Text(stringResource(R.string.payment_methods_remove_title)) },
            text = { Text(stringResource(R.string.payment_methods_remove_body)) },
            confirmButton = {
                TextAction(
                    text = stringResource(R.string.payment_methods_remove),
                    onClick = {
                        removing = null
                        onRemove(id)
                    },
                    modifier = Modifier.testTag(TAG_METHODS_REMOVE_CONFIRM),
                )
            },
            dismissButton = {
                TextAction(
                    text = stringResource(R.string.payment_methods_keep),
                    onClick = { removing = null },
                )
            },
        )
    }
}

/**
 * One method.
 *
 * @param row The method as the list draws it
 * @param onEdit Called to open the editor
 * @param onRemove Called to ask for removal
 */
@Composable
private fun MethodCard(
    row: MethodRow,
    onEdit: () -> Unit,
    onRemove: () -> Unit,
) {
    ShikkhokCard(modifier = Modifier.testTag(methodRowTag(row.methodId)), onClick = onEdit) {
        Text(
            text =
                stringResource(
                    if (row.kind == MethodKind.MOBILE) {
                        R.string.method_kind_mobile
                    } else {
                        R.string.method_kind_bank
                    },
                ),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(row.title, style = MaterialTheme.typography.titleMedium)
        Text(row.detail, style = MaterialTheme.typography.bodyLarge)
        row.extra?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
        row.note?.let {
            Text(
                text = "“$it”",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextAction(
                text = stringResource(R.string.payment_methods_remove),
                onClick = onRemove,
                modifier = Modifier.testTag(methodRemoveTag(row.methodId)),
            )
        }
    }
}
