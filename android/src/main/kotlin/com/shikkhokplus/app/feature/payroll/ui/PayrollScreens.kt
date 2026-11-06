package com.shikkhokplus.app.feature.payroll.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.network.SalaryLineDto
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.expenses.ui.MonthBar
import com.shikkhokplus.app.feature.myexams.Loadable
import com.shikkhokplus.app.feature.payroll.ADDITION
import com.shikkhokplus.app.feature.payroll.DEDUCTION
import com.shikkhokplus.app.feature.payroll.PayrollSheet
import com.shikkhokplus.app.feature.payroll.PayrollUiState

/** The draw-this-month button. */
const val TAG_PAYROLL_DRAW: String = "payroll_draw"

/** The open sheet's submit button. */
const val TAG_PAYROLL_SUBMIT: String = "payroll_submit"

/** The payroll's refusal. */
const val TAG_PAYROLL_FAILURE: String = "payroll_failure"

/**
 * Tag for one line's approve action.
 *
 * @param lineId The line
 * @return The tag
 */
fun payrollApproveTag(lineId: String): String = "payroll_approve_$lineId"

/**
 * Tag for one line's adjust action.
 *
 * @param lineId The line
 * @return The tag
 */
fun payrollAdjustTag(lineId: String): String = "payroll_adjust_$lineId"

/**
 * Tag for one line's pay action.
 *
 * @param lineId The line
 * @return The tag
 */
fun payrollPayTag(lineId: String): String = "payroll_pay_$lineId"

/**
 * What the payroll's controls call.
 *
 * @property onShift Moves the month by -1 or 1
 * @property onDraw Draws the month's lines
 * @property onApprove Approves a draft line
 * @property onOpenAdjust Opens the adjustment sheet for a draft line
 * @property onOpenPay Opens the payment sheet for an approved line
 * @property onRemoveAdjustment Removes an adjustment from a draft line
 * @property onKind Chooses the adjustment's kind
 * @property onLabel Types the adjustment's label
 * @property onAdjustAmount Types the adjustment's amount
 * @property onPayAmount Types the payment's amount
 * @property onPaidOn Types the payment's date
 * @property onNote Types the payment's note
 * @property onSubmit Sends the open sheet
 * @property onClose Closes the sheet
 * @property onRetry Reads again
 * @property onBack Leaves the screen
 */
data class PayrollActions(
    val onShift: (Long) -> Unit = {},
    val onDraw: () -> Unit = {},
    val onApprove: (String) -> Unit = {},
    val onOpenAdjust: (String) -> Unit = {},
    val onOpenPay: (String) -> Unit = {},
    val onRemoveAdjustment: (String, String) -> Unit = { _, _ -> },
    val onKind: (String) -> Unit = {},
    val onLabel: (String) -> Unit = {},
    val onAdjustAmount: (String) -> Unit = {},
    val onPayAmount: (String) -> Unit = {},
    val onPaidOn: (String) -> Unit = {},
    val onNote: (String) -> Unit = {},
    val onSubmit: () -> Unit = {},
    val onClose: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * A centre's payroll, a month at a time: draw the lines, add bonuses and
 * deductions to drafts, approve, and record payments.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun PayrollScreen(
    state: PayrollUiState,
    actions: PayrollActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.payroll_title),
        subtitle = stringResource(R.string.payroll_sub),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        MonthBar(state.month, state.canGoForward, actions.onShift)
        if (state.sheet == null) {
            state.failureKey?.let {
                Banner(
                    title = stringResource(MessageKeys.resolve(it)),
                    tone = BannerTone.ERROR,
                    modifier = Modifier.testTag(TAG_PAYROLL_FAILURE),
                )
            }
        }
        if (state.saved) Banner(title = stringResource(R.string.staff_saved))
        when (val lines = state.lines) {
            Loadable.Loading -> SkeletonList(rows = 3)
            is Loadable.Failed -> Failure(lines, actions.onRetry)
            is Loadable.Loaded -> {
                if (lines.value.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.payroll_title),
                        body = stringResource(R.string.payroll_empty),
                    )
                }
                lines.value.forEach { line -> SalaryCard(line, state.saving, actions) }
                PrimaryButton(
                    text = stringResource(R.string.payroll_draw),
                    onClick = actions.onDraw,
                    enabled = !state.saving,
                    modifier = Modifier.fillMaxWidth().testTag(TAG_PAYROLL_DRAW),
                )
            }
        }
    }
    state.sheet?.let { Sheet(state, it, actions) }
}

/**
 * One salary line, shared by the payroll and My pay; actions only on the payroll.
 *
 * @param line The line
 * @param saving Whether a write is in flight
 * @param actions What its controls call, or null for a read-only card
 * @param heading What the card is titled with: the person, or the month and centre
 */
@Composable
fun SalaryCard(
    line: SalaryLineDto,
    saving: Boolean = false,
    actions: PayrollActions? = null,
    heading: String = Numerals.freeText(line.staffName),
) {
    ShikkhokCard {
        val status = if (line.draft) R.string.payroll_status_draft else R.string.payroll_status_approved
        Text("$heading · ${stringResource(status)}", style = MaterialTheme.typography.titleMedium)
        Muted("${basisLine(line)} · ${stringResource(R.string.payroll_owed, Numerals.money(line.owed))}")
        Muted(
            stringResource(R.string.payroll_paid_remaining, Numerals.money(line.paid), Numerals.money(line.remaining)),
        )
        line.adjustments.forEach { adjustment ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                val sign = if (adjustment.kind == ADDITION) "+" else "−"
                Text(
                    "$sign ${Numerals.money(adjustment.amount)} · ${Numerals.freeText(adjustment.label)}",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.weight(1f),
                )
                if (actions != null && line.draft) {
                    TextAction(
                        text = stringResource(R.string.payroll_remove),
                        onClick = { actions.onRemoveAdjustment(line.lineId, adjustment.adjustmentId) },
                        enabled = !saving,
                    )
                }
            }
        }
        if (actions != null) LineActions(line, saving, actions)
    }
}

@Composable
private fun LineActions(line: SalaryLineDto, saving: Boolean, actions: PayrollActions) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (line.draft) {
            SecondaryButton(
                text = stringResource(R.string.payroll_adjust),
                onClick = { actions.onOpenAdjust(line.lineId) },
                enabled = !saving,
                modifier = Modifier.testTag(payrollAdjustTag(line.lineId)),
            )
            PrimaryButton(
                text = stringResource(R.string.payroll_approve),
                onClick = { actions.onApprove(line.lineId) },
                enabled = !saving,
                modifier = Modifier.testTag(payrollApproveTag(line.lineId)),
            )
        } else if (line.remaining.amount.signum() > 0) {
            PrimaryButton(
                text = stringResource(R.string.payroll_pay),
                onClick = { actions.onOpenPay(line.lineId) },
                enabled = !saving,
                modifier = Modifier.testTag(payrollPayTag(line.lineId)),
            )
        }
    }
}

@Composable
private fun basisLine(line: SalaryLineDto): String =
    if (line.basis == "monthly") {
        stringResource(R.string.payroll_basis_monthly, Numerals.money(line.rate))
    } else {
        stringResource(R.string.payroll_basis_per_class, Numerals.count(line.classesHeld), Numerals.money(line.rate))
    }

@Composable
private fun Muted(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun Failure(state: Loadable.Failed, onRetry: () -> Unit) {
    ErrorCard(
        title = stringResource(MessageKeys.resolve(state.messageKey)),
        body = null,
        retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
        onRetry = if (state.retryable) onRetry else null,
    )
}

@Composable
private fun Sheet(state: PayrollUiState, sheet: PayrollSheet, actions: PayrollActions) {
    val line = state.sheetLine
    val canSend =
        !state.saving &&
            when (sheet) {
                is PayrollSheet.Adjust -> sheet.body != null
                is PayrollSheet.Pay -> sheet.body != null
            }
    AlertDialog(
        onDismissRequest = actions.onClose,
        title = {
            Text(
                stringResource(
                    if (sheet is PayrollSheet.Pay) R.string.payroll_pay_title else R.string.payroll_adjust,
                ),
            )
        },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                line?.let { Muted(sheetSummary(it, sheet)) }
                when (sheet) {
                    is PayrollSheet.Adjust -> AdjustFields(sheet, actions)
                    is PayrollSheet.Pay -> PayFields(sheet, actions)
                }
                state.failureKey?.let {
                    Banner(
                        title = stringResource(MessageKeys.resolve(it)),
                        tone = BannerTone.ERROR,
                        modifier = Modifier.testTag(TAG_PAYROLL_FAILURE),
                    )
                }
            }
        },
        confirmButton = {
            TextAction(
                text = stringResource(if (sheet is PayrollSheet.Pay) R.string.payroll_pay else R.string.staff_save),
                onClick = actions.onSubmit,
                enabled = canSend,
                modifier = Modifier.testTag(TAG_PAYROLL_SUBMIT),
            )
        },
        dismissButton = { TextAction(text = stringResource(R.string.action_cancel), onClick = actions.onClose) },
    )
}

@Composable
private fun sheetSummary(line: SalaryLineDto, sheet: PayrollSheet): String {
    val figures =
        if (sheet is PayrollSheet.Pay) {
            stringResource(R.string.payroll_paid_remaining, Numerals.money(line.paid), Numerals.money(line.remaining))
        } else {
            stringResource(R.string.payroll_owed, Numerals.money(line.owed))
        }
    return "${Numerals.freeText(line.staffName)} · $figures"
}

@Composable
private fun AdjustFields(sheet: PayrollSheet.Adjust, actions: PayrollActions) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        FilterChip(
            selected = sheet.kind == ADDITION,
            onClick = { actions.onKind(ADDITION) },
            label = { Text(stringResource(R.string.payroll_addition)) },
        )
        FilterChip(
            selected = sheet.kind == DEDUCTION,
            onClick = { actions.onKind(DEDUCTION) },
            label = { Text(stringResource(R.string.payroll_deduction)) },
        )
    }
    ShikkhokTextField(
        value = sheet.label,
        onValueChange = actions.onLabel,
        label = stringResource(R.string.payroll_label),
    )
    ShikkhokTextField(
        value = sheet.amount,
        onValueChange = actions.onAdjustAmount,
        label = stringResource(R.string.payroll_amount),
        keyboardType = KeyboardType.Decimal,
    )
}

@Composable
private fun PayFields(sheet: PayrollSheet.Pay, actions: PayrollActions) {
    ShikkhokTextField(
        value = sheet.amount,
        onValueChange = actions.onPayAmount,
        label = stringResource(R.string.payroll_amount),
        keyboardType = KeyboardType.Decimal,
    )
    ShikkhokTextField(
        value = sheet.paidOn,
        onValueChange = actions.onPaidOn,
        label = stringResource(R.string.payroll_paid_on),
        placeholder = "YYYY-MM-DD",
    )
    ShikkhokTextField(value = sheet.note, onValueChange = actions.onNote, label = stringResource(R.string.payroll_note))
}

/**
 * My own pay, read-only: approved salary lines at every centre.
 *
 * @param state What to render
 * @param onRetry Reads again
 * @param modifier Layout modifier from the caller
 * @param bottomBar The lens's tab bar
 */
@Composable
fun MyPayScreen(
    state: Loadable<List<SalaryLineDto>>,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
) {
    ScreenScaffold(title = stringResource(R.string.my_pay_title), modifier = modifier, bottomBar = bottomBar) {
        when (state) {
            Loadable.Loading -> SkeletonList(rows = 2)
            is Loadable.Failed -> Failure(state, onRetry)
            is Loadable.Loaded ->
                if (state.value.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.my_pay_title),
                        body = stringResource(R.string.my_pay_empty),
                    )
                } else {
                    state.value.forEach { line ->
                        val heading = "${monthName(line.period, short = false)} · ${Numerals.freeText(line.centreName)}"
                        SalaryCard(line, heading = heading)
                    }
                }
        }
    }
}
