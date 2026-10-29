package com.shikkhokplus.app.feature.pay.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
import com.shikkhokplus.app.core.format.dateTimeLabel
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.pay.FormProblem
import com.shikkhokplus.app.feature.pay.PayForm
import com.shikkhokplus.app.feature.pay.PayMapper
import com.shikkhokplus.app.feature.pay.PayOption
import com.shikkhokplus.app.feature.pay.PayUiState

/** One fee on offer. */
const val TAG_PAY_OPTION: String = "pay_option"

/** The "Send for checking" button. */
const val TAG_PAY_SEND: String = "pay_send"

/** The transaction ID field. */
const val TAG_PAY_ID: String = "pay_id"

/** One app chip. */
const val TAG_PAY_CHANNEL: String = "pay_channel"

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
 * @property onChoose Pick a fee
 * @property onChange Back to the list of fees
 * @property onType The form changed
 * @property onSend Send for checking
 * @property onRetry Read again after a failed read
 */
data class PayActions(
    val onClose: () -> Unit = {},
    val onChoose: (PayOption) -> Unit = {},
    val onChange: () -> Unit = {},
    val onType: (PayForm) -> Unit = {},
    val onSend: () -> Unit = {},
    val onRetry: () -> Unit = {},
)

/**
 * S3: pay a fee by bKash, Nagad or Rocket, then send the transaction ID
 * for the teacher to check.
 *
 * Every amount and every list is the server's; the screen checks only
 * that what was typed has the shape of a payment.
 *
 * @param state What to render
 * @param actions What the buttons do
 */
@Composable
fun PayScreen(state: PayUiState, actions: PayActions) {
    ScreenScaffold(
        title = stringResource(if (state is PayUiState.Sent) R.string.pay_sent_title else R.string.pay_title),
        onBack = if (state is PayUiState.Filling && state.canChange) actions.onChange else actions.onClose,
        bottomBar = { BottomAction(state, actions) },
    ) {
        when (state) {
            PayUiState.Loading -> SkeletonList(rows = 3)
            is PayUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            is PayUiState.Choosing -> Choosing(state, actions)
            is PayUiState.Filling -> Filling(state, actions)
            is PayUiState.Sent -> Sent(state)
        }
    }
}

/**
 * The bar under the form: send, or done once sent.
 *
 * @param state What is shown
 * @param actions What the buttons do
 */
@Composable
private fun BottomAction(state: PayUiState, actions: PayActions) {
    val (label, enabled, onClick) =
        when (state) {
            is PayUiState.Sent -> Triple(stringResource(R.string.pay_done), true, actions.onClose)
            is PayUiState.Filling ->
                Triple(
                    stringResource(if (state.sending) R.string.pay_sending else R.string.pay_send),
                    !state.sending && PayMapper.claimOf(state.form).first != null,
                    actions.onSend,
                )
            is PayUiState.Choosing -> Triple(stringResource(R.string.pay_send), false, actions.onSend)
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

/**
 * "Which fee are you paying?", with the batches being checked named.
 *
 * @param state The choice
 * @param actions What the rows do
 */
@Composable
private fun ColumnScope.Choosing(state: PayUiState.Choosing, actions: PayActions) {
    if (state.options.isEmpty() && state.waiting.isEmpty()) {
        EmptyState(
            title = stringResource(R.string.pay_nothing_title),
            body = stringResource(R.string.pay_nothing_body),
        )
        return
    }
    if (state.options.isNotEmpty()) Label(stringResource(R.string.pay_which))
    state.options.forEach { option ->
        FeeBox(option, Modifier.clickable { actions.onChoose(option) }.testTag(TAG_PAY_OPTION)) {
            Box(Modifier.size(22.dp).border(2.dp, MaterialTheme.colorScheme.outline, CircleShape))
        }
    }
    state.waiting.forEach {
        Text(
            stringResource(
                R.string.pay_waiting_line,
                Numerals.freeText(it.batchName),
                monthName(it.period, short = false),
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    Text(
        stringResource(R.string.pay_how),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier =
            Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
                .padding(horizontal = 14.dp, vertical = 12.dp),
    )
}

/**
 * The form: for which fee, where to send, which app, the ID, the amount.
 *
 * @param state The form
 * @param actions What the fields do
 */
@Composable
private fun ColumnScope.Filling(state: PayUiState.Filling, actions: PayActions) {
    val form = state.form
    Label(stringResource(R.string.pay_for))
    FeeBox(state.option, if (state.canChange) Modifier.clickable(onClick = actions.onChange) else Modifier) {
        if (state.canChange) Text("›", style = MaterialTheme.typography.titleLarge)
    }
    Destination(state)
    Label(stringResource(R.string.pay_step_app))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        state.channels.forEach { channel ->
            ChannelChip(channel, selected = channel == form.channel, Modifier.weight(1f)) {
                actions.onType(form.copy(channel = channel))
            }
        }
    }
    ShikkhokTextField(
        value = form.transactionId,
        onValueChange = { actions.onType(form.copy(transactionId = it.uppercase())) },
        label = stringResource(R.string.pay_step_txn),
        error =
            state.problem?.takeIf { it == FormProblem.TRANSACTION_ID_SHORT }?.let {
                stringResource(R.string.pay_txn_short, form.channel ?: "")
            },
        modifier = Modifier.fillMaxWidth().testTag(TAG_PAY_ID),
        enabled = !state.sending,
    )
    state.failedKey?.let { key ->
        val offline = key == PayMapper.OFFLINE_KEY
        Banner(
            title =
                stringResource(if (offline) R.string.pay_offline_title else MessageKeys.resolve(key)),
            body = if (offline) stringResource(R.string.pay_offline_body) else null,
            tone = BannerTone.ERROR,
            modifier = Modifier.testTag(TAG_PAY_FAILED),
        )
    }
    ShikkhokTextField(
        value = form.amount,
        onValueChange = { actions.onType(form.copy(amount = it)) },
        label = stringResource(R.string.pay_amount),
        prefix = "৳",
        keyboardType = KeyboardType.Decimal,
        modifier = Modifier.fillMaxWidth(),
        enabled = !state.sending,
    )
}

/**
 * Step 1: where to send the money, with a Copy action.
 *
 * @param state The form
 */
@Composable
private fun Destination(state: PayUiState.Filling) {
    val destination = state.destination
    if (destination == null) {
        Text(stringResource(R.string.payment_ask_teacher), color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    val clipboard = LocalClipboardManager.current
    Row(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .padding(start = 14.dp, end = 8.dp, top = 10.dp, bottom = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                destination.teacherName?.let { stringResource(R.string.pay_step_send, Numerals.freeText(it)) }
                    ?: stringResource(R.string.pay_step_send_unnamed),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                Numerals.phone(destination.number),
                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
            )
            destination.service?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        TextAction(
            stringResource(R.string.pay_copy),
            { clipboard.setText(AnnotatedString(destination.number)) },
            Modifier.testTag(TAG_PAY_COPY),
        )
    }
}

/**
 * One app the money moved through.
 *
 * @param channel Its name
 * @param selected Whether it is chosen
 * @param modifier Its width
 * @param onClick Called when tapped
 */
@Composable
private fun ChannelChip(channel: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = if (selected) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface,
        border =
            if (selected) {
                BorderStroke(2.dp, MaterialTheme.colorScheme.primary)
            } else {
                BorderStroke(1.5.dp, MaterialTheme.colorScheme.outlineVariant)
            },
        modifier = modifier.heightIn(min = 44.dp).clickable(onClick = onClick).testTag(TAG_PAY_CHANNEL),
    ) {
        Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(vertical = 10.dp)) {
            Text(channel, style = MaterialTheme.typography.titleSmall)
        }
    }
}

/**
 * "Payment sent": what was sent, and that it shows as Verifying.
 *
 * @param state The sent payment
 */
@Composable
private fun ColumnScope.Sent(state: PayUiState.Sent) {
    val payment = state.payment
    Column(Modifier.testTag(TAG_PAY_SENT), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        PaymentStateChip(PaymentState.VERIFYING, stringResource(R.string.pay_verifying))
        Text(
            state.teacherName?.let { stringResource(R.string.pay_sent_check, Numerals.freeText(it), payment.channel) }
                ?: stringResource(R.string.pay_sent_check_unnamed, payment.channel),
            style = MaterialTheme.typography.bodyLarge,
        )
    }
    Column(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        SummaryRow(stringResource(R.string.pay_for), forLine(state.option))
        SummaryRow(stringResource(R.string.pay_amount_row), Numerals.money(payment.amount))
        payment.transactionId?.let { SummaryRow(stringResource(R.string.pay_id_row, payment.channel), it, mono = true) }
        SummaryRow(stringResource(R.string.pay_sent_row), dateTimeLabel(payment.submittedAt))
    }
    Text(
        stringResource(R.string.pay_sent_note),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/**
 * One line of the sent summary.
 *
 * @param label What it is
 * @param value Its value
 * @param mono Whether to set it as a code
 */
@Composable
private fun SummaryRow(label: String, value: String, mono: Boolean = false) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            value,
            style =
                MaterialTheme.typography.bodyMedium.copy(
                    fontWeight = FontWeight.SemiBold,
                    fontFamily = if (mono) FontFamily.Monospace else null,
                    letterSpacing = if (mono) 1.sp else MaterialTheme.typography.bodyMedium.letterSpacing,
                ),
        )
    }
}

/**
 * One fee in an outlined box: batch and month, then what is due by when.
 *
 * @param option The fee
 * @param modifier Click and tag
 * @param trailing Drawn at the end
 */
@Composable
private fun FeeBox(option: PayOption, modifier: Modifier, trailing: @Composable () -> Unit) {
    Row(
        modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .background(MaterialTheme.colorScheme.surface, RoundedCornerShape(8.dp))
            .border(1.5.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(8.dp))
            .padding(start = 14.dp, end = 12.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(forLine(option), style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold))
            Text(
                option.dueDate?.let {
                    stringResource(R.string.pay_due_by, Numerals.money(option.amountDue), shortDate(it))
                } ?: stringResource(R.string.pay_due, Numerals.money(option.amountDue)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        trailing()
    }
}

/**
 * "Physics · October".
 *
 * @param option The fee
 * @return The line
 */
@Composable
private fun forLine(option: PayOption): String =
    stringResource(R.string.pay_for_line, Numerals.freeText(option.batchName), monthName(option.period, short = false))

/**
 * A field label, 14/22 semibold as the board sets it.
 *
 * @param text The label
 */
@Composable
private fun Label(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold))
}
