package com.shikkhokplus.app.feature.pay.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.Surface
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dhakaTodayIso
import com.shikkhokplus.app.core.format.displayDate
import com.shikkhokplus.app.core.format.isoDate
import com.shikkhokplus.app.core.format.isoToUtcMillis
import com.shikkhokplus.app.core.network.PaymentMethodDto
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.pay.FormProblem
import com.shikkhokplus.app.feature.pay.PayChoice
import com.shikkhokplus.app.feature.pay.PayForm
import com.shikkhokplus.app.feature.pay.PayMapper
import com.shikkhokplus.app.feature.pay.PayScope
import com.shikkhokplus.app.feature.pay.PayUiState
import com.shikkhokplus.app.feature.pay.SentOutcome

/** One listed method on the choose screen. */
const val TAG_PAY_METHOD: String = "pay_method"

/** The "Cash in hand" row on the choose screen. */
const val TAG_PAY_CASH: String = "pay_cash"

/** One batch in the batch picker. */
const val TAG_PAY_BATCH: String = "pay_batch"

/** One child's checkbox in the "For" field. */
const val TAG_PAY_CHILD: String = "pay_child"

/** The "Send for checking" button. */
const val TAG_PAY_SEND: String = "pay_send"

/** The transaction ID field. */
const val TAG_PAY_ID: String = "pay_id"

/** The paying-account field. */
const val TAG_PAY_ACCOUNT: String = "pay_account"

/** The amount field. */
const val TAG_PAY_AMOUNT: String = "pay_amount"

/** The date-paid field. */
const val TAG_PAY_DATE: String = "pay_date"

/** The owed line under "For". */
const val TAG_PAY_OWED: String = "pay_owed"

/** The copy-number action. */
const val TAG_PAY_COPY: String = "pay_copy"

/** The sent confirmation. */
const val TAG_PAY_SENT: String = "pay_sent"

/** Why the last send failed. */
const val TAG_PAY_FAILED: String = "pay_failed"

/**
 * What the screen's buttons do.
 *
 * @property onClose Leave the flow
 * @property onChoose Pick a way of paying
 * @property onBack Back to the list of methods
 * @property onBatch Pick another batch
 * @property onToggleChild Add or drop a child
 * @property onType The form changed
 * @property onSend Send for checking
 * @property onRetry Read again after a failed read
 */
data class PayActions(
    val onClose: () -> Unit = {},
    val onChoose: (PayChoice) -> Unit = {},
    val onBack: () -> Unit = {},
    val onBatch: (String) -> Unit = {},
    val onToggleChild: (String) -> Unit = {},
    val onType: (PayForm) -> Unit = {},
    val onSend: () -> Unit = {},
    val onRetry: () -> Unit = {},
)

/**
 * F1 to F5's pay flow: choose how to pay, fill in the details, send the
 * payment for the teacher to check.
 *
 * Every amount and every list is the server's; the screen checks only
 * that what was typed has the shape of a payment.
 *
 * @param state What to render
 * @param actions What the buttons do
 * @param todayIso Bangladesh's today; the date picker offers nothing later
 */
@Composable
fun PayScreen(state: PayUiState, actions: PayActions, todayIso: String = dhakaTodayIso()) {
    ScreenScaffold(
        title = stringResource(titleOf(state)),
        onBack = if (state is PayUiState.Filling) actions.onBack else actions.onClose,
        bottomBar = { BottomAction(state, actions) },
    ) {
        when (state) {
            PayUiState.Loading -> SkeletonList(rows = 3)
            PayUiState.NoSeats ->
                EmptyState(
                    title = stringResource(R.string.pay_nothing_title),
                    body = stringResource(R.string.pay_nothing_body),
                )
            is PayUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            is PayUiState.Methods -> Methods(state.scope, actions)
            is PayUiState.Filling -> Filling(state, actions, todayIso)
            is PayUiState.Sent -> Sent(state)
        }
    }
}

private fun titleOf(state: PayUiState): Int =
    when {
        state is PayUiState.Sent && state.outcome != SentOutcome.PENDING -> R.string.pay_recorded_title
        state is PayUiState.Sent -> R.string.pay_sent_title
        state is PayUiState.Methods -> R.string.pay_choose_title
        state is PayUiState.Filling && state.choice is PayChoice.Cash -> R.string.pay_cash
        state is PayUiState.Filling && (state.choice as PayChoice.Method).method.kind == "bank" ->
            R.string.pay_bank_title
        state is PayUiState.Filling -> R.string.pay_mobile_title
        else -> R.string.pay_title
    }

@Composable
private fun BottomAction(state: PayUiState, actions: PayActions) {
    val (label, enabled, onClick) =
        when (state) {
            is PayUiState.Sent -> Triple(stringResource(R.string.pay_done), true, actions.onClose)
            is PayUiState.Filling ->
                Triple(
                    stringResource(if (state.sending) R.string.pay_sending else R.string.pay_send),
                    !state.sending && PayMapper.requestOf(state).first != null,
                    actions.onSend,
                )
            else -> return
        }
    Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)) {
        HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
        PrimaryButton(
            text = label,
            onClick = onClick,
            enabled = enabled,
            modifier = Modifier.fillMaxWidth().padding(16.dp).testTag(TAG_PAY_SEND),
        )
    }
}

@Composable
private fun ColumnScope.Methods(scope: PayScope, actions: PayActions) {
    BatchPicker(scope, actions)
    Text(stringResource(R.string.pay_choose_heading), style = MaterialTheme.typography.titleLarge)
    Text(
        scope.teacherName?.let { stringResource(R.string.pay_choose_sub, Numerals.freeText(it)) }
            ?: stringResource(R.string.pay_choose_sub_unnamed),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    val mobile = scope.methods.filter { it.kind == "mobile" }
    val bank = scope.methods.filter { it.kind == "bank" }
    if (mobile.isNotEmpty()) Label(stringResource(R.string.pay_group_mobile))
    mobile.forEach { method ->
        MethodRow(method.provider.orEmpty(), Numerals.phone(method.mobileNumber.orEmpty()), TAG_PAY_METHOD) {
            actions.onChoose(PayChoice.Method(method))
        }
    }
    if (bank.isNotEmpty()) Label(stringResource(R.string.pay_group_bank))
    bank.forEach { method ->
        MethodRow(method.provider.orEmpty(), method.branchName.orEmpty(), TAG_PAY_METHOD) {
            actions.onChoose(PayChoice.Method(method))
        }
    }
    MethodRow(stringResource(R.string.pay_cash), stringResource(R.string.pay_cash_hint), TAG_PAY_CASH) {
        actions.onChoose(PayChoice.Cash)
    }
    if (scope.methods.isEmpty()) {
        Text(
            stringResource(R.string.pay_no_methods),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun MethodRow(title: String, detail: String, tag: String, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(8.dp))
            .border(1.5.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 8.dp)
            .testTag(tag),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                Numerals.freeText(title),
                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
            )
            if (detail.isNotEmpty()) {
                Text(
                    detail,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Text("›", style = MaterialTheme.typography.titleLarge)
    }
}

@Composable
private fun ColumnScope.BatchPicker(scope: PayScope, actions: PayActions) {
    Label(stringResource(R.string.pay_batch))
    if (scope.batches.size == 1) {
        Text(Numerals.freeText(scope.batch.name), style = MaterialTheme.typography.bodyLarge)
        return
    }
    scope.batches.forEach { batch ->
        val selected = batch.key == scope.batch.key
        Surface(
            shape = RoundedCornerShape(10.dp),
            color = if (selected) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface,
            border =
                BorderStroke(
                    if (selected) 2.dp else 1.5.dp,
                    if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
                ),
            modifier =
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp)
                    .clickable { actions.onBatch(batch.key) }
                    .testTag(TAG_PAY_BATCH),
        ) {
            Row(
                Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(Numerals.freeText(batch.name), style = MaterialTheme.typography.titleSmall)
            }
        }
    }
}

@Composable
private fun ColumnScope.Filling(state: PayUiState.Filling, actions: PayActions, todayIso: String) {
    val form = state.form
    val choice = state.choice
    when (choice) {
        is PayChoice.Method -> Destination(choice.method)
        PayChoice.Cash ->
            Text(stringResource(R.string.pay_cash_help), color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
    BatchPicker(state.scope, actions)
    ForField(state, actions)
    state.owed?.let { owed ->
        val names = joined(owed.children.map { Numerals.freeText(it.displayName) })
        Text(
            if (owed.owedTogether.amount.signum() > 0) {
                stringResource(R.string.pay_owed_for, names, Numerals.money(owed.owedTogether))
            } else {
                stringResource(R.string.pay_owed_nothing, names)
            },
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.testTag(TAG_PAY_OWED),
        )
    }
    val kind = (choice as? PayChoice.Method)?.method?.kind
    if (kind == "mobile") {
        ShikkhokTextField(
            value = form.transactionId,
            onValueChange = { actions.onType(form.copy(transactionId = it.uppercase())) },
            label = stringResource(R.string.pay_txn_label),
            error =
                state.problem?.takeIf { it == FormProblem.TRANSACTION_ID_SHORT }?.let {
                    stringResource(R.string.pay_txn_short, (choice as PayChoice.Method).method.provider.orEmpty())
                },
            modifier = Modifier.fillMaxWidth().testTag(TAG_PAY_ID),
            enabled = !state.sending,
        )
    }
    if (kind == "bank") {
        ShikkhokTextField(
            value = form.fromAccount,
            onValueChange = { actions.onType(form.copy(fromAccount = it)) },
            label = stringResource(R.string.pay_from_account),
            modifier = Modifier.fillMaxWidth().testTag(TAG_PAY_ACCOUNT),
            enabled = !state.sending,
        )
    }
    ShikkhokTextField(
        value = form.amount,
        onValueChange = { actions.onType(form.copy(amount = it)) },
        label = stringResource(R.string.pay_amount),
        prefix = "৳",
        keyboardType = KeyboardType.Decimal,
        modifier = Modifier.fillMaxWidth().testTag(TAG_PAY_AMOUNT),
        enabled = !state.sending,
    )
    DateField(form.paidOn, todayIso, !state.sending) { actions.onType(form.copy(paidOn = it)) }
    ShikkhokTextField(
        value = form.note,
        onValueChange = { actions.onType(form.copy(note = it)) },
        label = stringResource(R.string.pay_note),
        modifier = Modifier.fillMaxWidth(),
        enabled = !state.sending,
        singleLine = false,
    )
    state.failedKey?.let { key ->
        val offline = key == PayMapper.OFFLINE_KEY
        Banner(
            title = stringResource(if (offline) R.string.pay_offline_title else MessageKeys.resolve(key)),
            body = if (offline) stringResource(R.string.pay_offline_body) else null,
            tone = BannerTone.ERROR,
            modifier = Modifier.testTag(TAG_PAY_FAILED),
        )
    }
}

@Composable
private fun ColumnScope.ForField(state: PayUiState.Filling, actions: PayActions) {
    val seats = state.scope.batch.seats
    Label(stringResource(R.string.pay_for))
    if (seats.size == 1) {
        Text(
            seats.single().childName?.let { Numerals.freeText(it) } ?: stringResource(R.string.pay_for_self),
            style = MaterialTheme.typography.bodyLarge,
        )
        return
    }
    seats.forEach { seat ->
        Row(
            Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag(TAG_PAY_CHILD),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Checkbox(
                checked = seat.enrollmentId in state.scope.selected,
                onCheckedChange = { actions.onToggleChild(seat.enrollmentId) },
                enabled = !state.sending,
            )
            Text(Numerals.freeText(seat.childName.orEmpty()), style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun joined(names: List<String>): String =
    when (names.size) {
        0 -> ""
        1 -> names.single()
        else -> names.dropLast(1).joinToString(", ") + " " + stringResource(R.string.pay_and) + " " + names.last()
    }

@Composable
private fun Destination(method: PaymentMethodDto) {
    val clipboard = LocalClipboardManager.current
    val bank = method.kind == "bank"
    Column(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .padding(start = 14.dp, end = 8.dp, top = 10.dp, bottom = 10.dp),
    ) {
        if (bank) {
            DetailRow(stringResource(R.string.pay_bank_name), method.provider)
            DetailRow(stringResource(R.string.pay_branch), method.branchName)
            DetailRow(stringResource(R.string.pay_account_name), method.accountName)
        } else {
            Text(
                stringResource(R.string.pay_send_to),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        val number = if (bank) method.accountNumber.orEmpty() else method.mobileNumber.orEmpty()
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                if (bank) {
                    Text(
                        stringResource(R.string.pay_account_no),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(
                    if (bank) number else Numerals.phone(number),
                    style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                )
                if (!bank) {
                    Text(
                        method.provider.orEmpty(),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            TextAction(
                stringResource(R.string.pay_copy),
                { clipboard.setText(AnnotatedString(number)) },
                Modifier.testTag(TAG_PAY_COPY),
            )
        }
        method.note?.takeIf { it.isNotBlank() }?.let {
            Text(
                Numerals.freeText(it),
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
    Text(
        if (bank) {
            stringResource(R.string.pay_bank_help)
        } else {
            stringResource(R.string.pay_mobile_help, method.provider.orEmpty())
        },
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun DetailRow(label: String, value: String?) {
    if (value.isNullOrBlank()) return
    Row(Modifier.fillMaxWidth().padding(bottom = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            Numerals.freeText(value),
            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold),
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DateField(paidOn: String, todayIso: String, enabled: Boolean, onPick: (String) -> Unit) {
    var picking by remember { mutableStateOf(false) }
    val latest = isoToUtcMillis(todayIso) ?: Long.MAX_VALUE
    Label(stringResource(R.string.pay_date))
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surface,
        border = BorderStroke(1.5.dp, MaterialTheme.colorScheme.outline),
        modifier =
            Modifier
                .fillMaxWidth()
                .heightIn(min = 48.dp)
                .clickable(enabled = enabled) { picking = true }
                .testTag(TAG_PAY_DATE),
    ) {
        Row(Modifier.padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(isoToUtcMillis(paidOn)?.let(::displayDate) ?: paidOn, style = MaterialTheme.typography.bodyLarge)
        }
    }
    if (picking) {
        val picker =
            rememberDatePickerState(
                initialSelectedDateMillis = isoToUtcMillis(paidOn),
                selectableDates =
                    object : SelectableDates {
                        override fun isSelectableDate(utcTimeMillis: Long): Boolean = utcTimeMillis <= latest
                    },
            )
        DatePickerDialog(
            onDismissRequest = { picking = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        picker.selectedDateMillis?.let { onPick(isoDate(it)) }
                        picking = false
                    },
                ) { Text(stringResource(R.string.action_ok)) }
            },
            dismissButton = {
                TextButton(onClick = { picking = false }) {
                    Text(stringResource(R.string.action_cancel))
                }
            },
        ) { DatePicker(state = picker) }
    }
}

@Composable
private fun ColumnScope.Sent(state: PayUiState.Sent) {
    val teacher = state.teacherName?.let { Numerals.freeText(it) } ?: stringResource(R.string.pay_teacher_fallback)
    val amount = Numerals.money(state.payment.totalAmount)
    val body = sentBody(state, teacher, amount)
    Column(Modifier.testTag(TAG_PAY_SENT), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        when (state.outcome) {
            SentOutcome.PENDING -> PaymentStateChip(PaymentState.VERIFYING, stringResource(R.string.pay_pending))
            SentOutcome.APPROVED -> PaymentStateChip(PaymentState.PAID, stringResource(R.string.inbox_outcome_approved))
            // No chip state means "refused"; the status row below says it.
            SentOutcome.REJECTED -> Unit
        }
        Text(body, style = MaterialTheme.typography.bodyLarge)
    }
    Column(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        SummaryRow(
            stringResource(R.string.pay_for),
            stringResource(
                R.string.pay_for_line,
                joined(state.payment.claims.map { Numerals.freeText(it.displayName) }.distinct()),
                Numerals.freeText(state.batchName),
            ),
        )
        SummaryRow(stringResource(R.string.pay_amount_row), amount)
        SummaryRow(
            stringResource(R.string.pay_paid_on_row),
            isoToUtcMillis(state.payment.paidOn)?.let(::displayDate) ?: state.payment.paidOn,
        )
        // The transaction ID the teacher will match against their SMS (S3).
        state.reference?.let { SummaryRow(stringResource(R.string.verify_transaction_id), Numerals.transactionId(it)) }
        SummaryRow(stringResource(R.string.pay_status_row), stringResource(statusOf(state.outcome)))
    }
    // **Says what the fee shows meanwhile** (S3), so a family who sees
    // "Verifying" on the batch does not think the payment went missing.
    if (state.outcome == SentOutcome.PENDING) {
        Text(
            stringResource(R.string.pay_until_verified),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * What the sent page says happened.
 *
 * A resend the teacher already decided says so, rather than "will
 * check": the server answers a replay with the original submission and
 * its stored status.
 *
 * @param state The sent page
 * @param teacher Who checks it, already formatted
 * @param amount The amount, already formatted
 * @return The body text
 */
@Composable
private fun sentBody(state: PayUiState.Sent, teacher: String, amount: String): String =
    when (state.outcome) {
        SentOutcome.APPROVED -> stringResource(R.string.pay_recorded_body_approved, amount, teacher)
        SentOutcome.REJECTED -> stringResource(R.string.pay_recorded_body_rejected, amount, teacher)
        SentOutcome.PENDING ->
            when (val choice = state.choice) {
                PayChoice.Cash -> stringResource(R.string.pay_sent_body_cash, teacher, amount)
                is PayChoice.Method ->
                    if (choice.method.kind == "bank") {
                        stringResource(R.string.pay_sent_body_bank, teacher, amount, state.reference.orEmpty())
                    } else {
                        stringResource(
                            R.string.pay_sent_body_mobile,
                            teacher,
                            amount,
                            choice.method.provider.orEmpty(),
                            state.reference.orEmpty(),
                        )
                    }
            }
    }

/**
 * The status row's text for where the server's record stands.
 *
 * @param outcome The server's status, as read
 * @return A string resource
 */
private fun statusOf(outcome: SentOutcome): Int =
    when (outcome) {
        SentOutcome.PENDING -> R.string.pay_pending
        SentOutcome.APPROVED -> R.string.inbox_outcome_approved
        SentOutcome.REJECTED -> R.string.inbox_outcome_rejected
    }

@Composable
private fun SummaryRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold))
    }
}

@Composable
private fun Label(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold))
}
