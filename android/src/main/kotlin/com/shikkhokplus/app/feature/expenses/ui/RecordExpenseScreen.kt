package com.shikkhokplus.app.feature.expenses.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.format.isoDate
import com.shikkhokplus.app.core.format.isoToUtcMillis
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.expenses.ExpenseCategory
import com.shikkhokplus.app.feature.expenses.RecordExpenseUiState

/** The description field. */
const val TAG_EXPENSE_WHAT: String = "expense_what"

/** The amount field. */
const val TAG_EXPENSE_AMOUNT: String = "expense_amount"

/** The date control. */
const val TAG_EXPENSE_DATE: String = "expense_date"

/** The save button. */
const val TAG_EXPENSE_SAVE: String = "expense_save"

/** The refusal under the form. */
const val TAG_EXPENSE_FAILURE: String = "expense_failure"

/**
 * Tag for one category chip.
 *
 * @param category The category
 * @return The tag
 */
fun expenseCategoryTag(category: ExpenseCategory): String = "expense_category_${category.wire}"

/**
 * What the record form's controls call.
 *
 * @property onCategory Chooses a category
 * @property onWhat Edits the description
 * @property onAmount Edits the amount
 * @property onSpentOn Picks the date, `yyyy-MM-dd`
 * @property onPayee Edits who was paid
 * @property onNote Edits the note
 * @property onSave Sends the form
 * @property onCancel Leaves without saving
 */
data class RecordExpenseActions(
    val onCategory: (ExpenseCategory) -> Unit = {},
    val onWhat: (String) -> Unit = {},
    val onAmount: (String) -> Unit = {},
    val onSpentOn: (String) -> Unit = {},
    val onPayee: (String) -> Unit = {},
    val onNote: (String) -> Unit = {},
    val onSave: () -> Unit = {},
    val onCancel: () -> Unit = {},
)

/**
 * Record an expense: category, what, amount, date, and optionally who was
 * paid and a note. The server checks every value.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
fun RecordExpenseScreen(
    state: RecordExpenseUiState,
    actions: RecordExpenseActions,
    modifier: Modifier = Modifier,
) {
    var picking by remember { mutableStateOf(false) }

    ScreenScaffold(
        title = stringResource(R.string.expenses_record),
        modifier = modifier,
        onBack = actions.onCancel,
    ) {
        Text(stringResource(R.string.expenses_category), style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ExpenseCategory.entries.forEach { category ->
                FilterChip(
                    selected = state.category == category,
                    onClick = { actions.onCategory(category) },
                    label = { Text(stringResource(categoryLabel(category))) },
                    modifier = Modifier.testTag(expenseCategoryTag(category)),
                )
            }
        }
        ShikkhokTextField(
            value = state.what,
            onValueChange = actions.onWhat,
            label = stringResource(R.string.expenses_what),
            fieldModifier = Modifier.testTag(TAG_EXPENSE_WHAT),
        )
        ShikkhokTextField(
            value = state.typedAmount,
            onValueChange = actions.onAmount,
            label = stringResource(R.string.expenses_amount),
            prefix = "৳",
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            fieldModifier = Modifier.testTag(TAG_EXPENSE_AMOUNT),
        )
        Text(stringResource(R.string.expenses_spent_on), style = MaterialTheme.typography.labelLarge)
        SecondaryButton(
            text = shortDate(state.spentOn),
            onClick = { picking = true },
            modifier = Modifier.fillMaxWidth().testTag(TAG_EXPENSE_DATE),
        )
        ShikkhokTextField(
            value = state.payee,
            onValueChange = actions.onPayee,
            label = stringResource(R.string.expenses_payee),
        )
        ShikkhokTextField(
            value = state.note,
            onValueChange = actions.onNote,
            label = stringResource(R.string.expenses_note),
        )
        state.failureKey?.let {
            Banner(
                title = stringResource(MessageKeys.resolve(it)),
                tone = BannerTone.ERROR,
                modifier = Modifier.testTag(TAG_EXPENSE_FAILURE),
            )
        }
        PrimaryButton(
            text = stringResource(R.string.expenses_save),
            onClick = actions.onSave,
            enabled = state.canSave,
            modifier = Modifier.fillMaxWidth().testTag(TAG_EXPENSE_SAVE),
        )
        SecondaryButton(
            text = stringResource(R.string.action_cancel),
            onClick = actions.onCancel,
            modifier = Modifier.fillMaxWidth(),
        )
    }

    if (picking) {
        val picker = rememberDatePickerState(initialSelectedDateMillis = isoToUtcMillis(state.spentOn))
        DatePickerDialog(
            onDismissRequest = { picking = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        picker.selectedDateMillis?.let { actions.onSpentOn(isoDate(it)) }
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
