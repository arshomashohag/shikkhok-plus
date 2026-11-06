package com.shikkhokplus.app.feature.expenses.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.expenses.ExpenseRow
import com.shikkhokplus.app.feature.expenses.ExpensesBody
import com.shikkhokplus.app.feature.expenses.ExpensesUiState

/** The record-an-expense action. */
const val TAG_EXPENSES_RECORD: String = "expenses_record"

/** The empty month. */
const val TAG_EXPENSES_EMPTY: String = "expenses_empty"

/** The month's total. */
const val TAG_EXPENSES_TOTAL: String = "expenses_total"

/** The confirm button in the void dialog. */
const val TAG_EXPENSES_VOID_CONFIRM: String = "expenses_void_confirm"

/** The reason field in the void dialog. */
const val TAG_EXPENSES_VOID_REASON: String = "expenses_void_reason"

/**
 * Tag for one expense row.
 *
 * @param expenseId The expense
 * @return The tag
 */
fun expenseRowTag(expenseId: String): String = "expense_row_$expenseId"

/**
 * Tag for one row's void action.
 *
 * @param expenseId The expense
 * @return The tag
 */
fun expenseVoidTag(expenseId: String): String = "expense_void_$expenseId"

/**
 * Where the expense list leads.
 *
 * @property onShift Moves the month by -1 or 1
 * @property onRecord Opens the record form
 * @property onVoid Voids an expense with an optional reason, once confirmed
 * @property onRetry Reads again after a failure
 * @property onOpenSummary Opens the monthly summary
 * @property onBack Leaves the screen
 */
data class ExpensesActions(
    val onShift: (Long) -> Unit = {},
    val onRecord: () -> Unit = {},
    val onVoid: (String, String) -> Unit = { _, _ -> },
    val onRetry: () -> Unit = {},
    val onOpenSummary: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * Expenses: one month's spending, voiding an expense, and the server's
 * totals by category. A voided expense stays listed, crossed out.
 *
 * @param state What to render
 * @param actions Where each control leads
 * @param modifier Layout modifier from the caller
 */
@Composable
fun ExpensesScreen(
    state: ExpensesUiState,
    actions: ExpensesActions,
    modifier: Modifier = Modifier,
) {
    var voiding by remember { mutableStateOf<ExpenseRow?>(null) }

    ScreenScaffold(
        title = stringResource(R.string.expenses_title),
        subtitle = stringResource(R.string.summary_basis),
        modifier = modifier,
        onBack = actions.onBack,
        actions = { TextAction(stringResource(R.string.money_open_summary), actions.onOpenSummary) },
    ) {
        MonthBar(state.month, state.canGoForward, actions.onShift)
        state.voidFailedKey?.let {
            Banner(title = stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR)
        }
        when (val body = state.body) {
            ExpensesBody.Loading -> SkeletonList(rows = 3)
            ExpensesBody.Empty ->
                EmptyState(
                    title = stringResource(R.string.expenses_title),
                    body = stringResource(R.string.expenses_empty),
                    modifier = Modifier.testTag(TAG_EXPENSES_EMPTY),
                )
            is ExpensesBody.Loaded -> {
                ShikkhokCard(modifier = Modifier.testTag(TAG_EXPENSES_TOTAL)) {
                    Text(
                        text = stringResource(R.string.expenses_month_total, Numerals.money(body.total)),
                        style = MaterialTheme.typography.headlineSmall,
                    )
                }
                body.rows.forEach { row -> ExpenseCard(row, onVoid = { voiding = row }) }
                if (body.byCategory.isNotEmpty()) {
                    CategoryLines(stringResource(R.string.expenses_by_category), body.byCategory)
                }
            }
            is ExpensesBody.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = stringResource(R.string.expenses_load_failed),
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) actions.onRetry else null,
                )
        }
        if (state.body !is ExpensesBody.Loading) {
            PrimaryButton(
                text = stringResource(R.string.expenses_record),
                onClick = actions.onRecord,
                modifier = Modifier.fillMaxWidth().testTag(TAG_EXPENSES_RECORD),
            )
        }
    }

    voiding?.let { row ->
        VoidDialog(
            row = row,
            onConfirm = { reason ->
                voiding = null
                actions.onVoid(row.expenseId, reason)
            },
            onDismiss = { voiding = null },
        )
    }
}

/**
 * One expense. A voided one is crossed out, says why, and offers nothing.
 *
 * @param row The expense
 * @param onVoid Called to ask for a void
 */
@Composable
private fun ExpenseCard(row: ExpenseRow, onVoid: () -> Unit) {
    val strike = if (row.voided) TextDecoration.LineThrough else TextDecoration.None
    ShikkhokCard(modifier = Modifier.testTag(expenseRowTag(row.expenseId))) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(row.what, style = MaterialTheme.typography.titleMedium, textDecoration = strike)
                Text(
                    text =
                        listOfNotNull(
                            stringResource(categoryLabel(row.category)),
                            shortDate(row.spentOn),
                            row.payee,
                        ).joinToString(" · "),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (row.voided) {
                    Text(
                        text =
                            listOfNotNull(stringResource(R.string.expenses_voided), row.voidReason)
                                .joinToString(" · "),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
            Text(Numerals.money(row.amount), style = MaterialTheme.typography.titleMedium, textDecoration = strike)
        }
        if (!row.voided) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextAction(
                    text = stringResource(R.string.expenses_void),
                    onClick = onVoid,
                    modifier = Modifier.testTag(expenseVoidTag(row.expenseId)),
                )
            }
        }
    }
}

/**
 * Confirm a void, with an optional reason.
 *
 * @param row The expense
 * @param onConfirm Called with the typed reason
 * @param onDismiss Called to keep it
 */
@Composable
private fun VoidDialog(
    row: ExpenseRow,
    onConfirm: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var reason by remember(row.expenseId) { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.expenses_void_title)) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("${row.what} · ${Numerals.money(row.amount)}", style = MaterialTheme.typography.titleSmall)
                Text(stringResource(R.string.expenses_void_body))
                ShikkhokTextField(
                    value = reason,
                    onValueChange = { reason = it },
                    label = stringResource(R.string.expenses_void_reason),
                    fieldModifier = Modifier.testTag(TAG_EXPENSES_VOID_REASON),
                )
            }
        },
        confirmButton = {
            TextAction(
                text = stringResource(R.string.expenses_void),
                onClick = { onConfirm(reason) },
                modifier = Modifier.testTag(TAG_EXPENSES_VOID_CONFIRM),
            )
        },
        dismissButton = { TextAction(stringResource(R.string.action_cancel), onDismiss) },
    )
}
