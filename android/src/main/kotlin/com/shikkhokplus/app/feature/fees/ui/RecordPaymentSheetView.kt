package com.shikkhokplus.app.feature.fees.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.fees.RecordSheet
import com.shikkhokplus.app.feature.fees.RecordSide
import com.shikkhokplus.app.feature.verify.ui.CarryOrWaive

/** The "Record payment" action on the fee history. */
const val TAG_FEES_RECORD: String = "fees_record"

/** The confirmation shown once a record was accepted. */
const val TAG_FEES_RECORDED: String = "fees_recorded"

/** The record sheet's amount field. */
const val TAG_RECORD_AMOUNT: String = "record_amount"

/** One channel chip; the channel follows an underscore. */
const val TAG_RECORD_CHANNEL: String = "record_channel"

/** The record sheet's reference field. */
const val TAG_RECORD_REFERENCE: String = "record_reference"

/** The record sheet's note field. */
const val TAG_RECORD_NOTE: String = "record_note"

/** The record sheet's confirm button. */
const val TAG_RECORD_CONFIRM: String = "record_confirm"

/** The line saying how the typed amount compares with what is owed. */
const val TAG_RECORD_LINE: String = "record_line"

/**
 * What the record sheet can do.
 *
 * @property onType The amount received, as typed
 * @property onChannel `cash` or a mobile service
 * @property onReference The reference, as typed
 * @property onNote The note to the family
 * @property onDisposition `carried` or `waived`
 * @property onConfirm Send the record
 * @property onDismiss Close without recording
 */
class RecordActions(
    val onType: (String) -> Unit,
    val onChannel: (String) -> Unit,
    val onReference: (String) -> Unit,
    val onNote: (String) -> Unit,
    val onDisposition: (String) -> Unit,
    val onConfirm: () -> Unit,
    val onDismiss: () -> Unit,
)

/**
 * "Record payment": the teacher records money received by hand.
 *
 * **Renders a [RecordSheet] and decides nothing.** Whether carry or
 * waive is asked comes from the sheet's comparison of the typed amount
 * with the server's figure, and the server re-checks it. The choice
 * itself is the approval sheet's [CarryOrWaive], in the same words.
 *
 * @param sheet The sheet's state
 * @param actions What the sheet can do
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun RecordPaymentSheetView(
    sheet: RecordSheet,
    actions: RecordActions,
) {
    val received = sheet.received
    ModalBottomSheet(
        onDismissRequest = actions.onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = MaterialTheme.colorScheme.surface,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(stringResource(R.string.fees_record_title), style = MaterialTheme.typography.titleLarge)
            Text(
                stringResource(R.string.fees_record_owed, Numerals.money(sheet.owed)),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            sheet.errorKey?.let {
                Banner(title = stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR)
            }
            ShikkhokTextField(
                value = sheet.typed,
                onValueChange = actions.onType,
                label = stringResource(R.string.verify_received_amount),
                prefix = "৳",
                error = stringResource(R.string.fee_invalid).takeIf { received == null && sheet.typed.isNotEmpty() },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                fieldModifier = Modifier.testTag(TAG_RECORD_AMOUNT),
            )
            ComparisonLine(sheet.side)
            if (sheet.needsDisposition) {
                CarryOrWaive(selected = sheet.disposition, shortfall = null, onChoose = actions.onDisposition)
            }
            Text(stringResource(R.string.fees_record_channel), style = MaterialTheme.typography.labelLarge)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                RecordSheet.CHANNELS.forEach { channel ->
                    FilterChip(
                        selected = sheet.channel == channel,
                        onClick = { actions.onChannel(channel) },
                        label = {
                            Text(
                                if (channel == RecordSheet.CASH) {
                                    stringResource(R.string.fees_record_channel_cash)
                                } else {
                                    channel
                                },
                            )
                        },
                        modifier = Modifier.testTag("${TAG_RECORD_CHANNEL}_$channel"),
                    )
                }
            }
            ShikkhokTextField(
                value = sheet.reference,
                onValueChange = actions.onReference,
                label = stringResource(R.string.fees_record_reference),
                fieldModifier = Modifier.testTag(TAG_RECORD_REFERENCE),
            )
            ShikkhokTextField(
                value = sheet.note,
                onValueChange = actions.onNote,
                label = stringResource(R.string.fees_record_note),
                singleLine = false,
                minLines = 2,
                fieldModifier = Modifier.testTag(TAG_RECORD_NOTE),
            )
            PrimaryButton(
                text = stringResource(R.string.fees_record_confirm, received?.let(Numerals::money) ?: sheet.typed),
                onClick = actions.onConfirm,
                enabled = sheet.canConfirm,
                modifier = Modifier.fillMaxWidth().testTag(TAG_RECORD_CONFIRM),
            )
            TextAction(stringResource(R.string.action_cancel), actions.onDismiss, Modifier.fillMaxWidth())
        }
    }
}

/**
 * How the typed amount stands against what is owed, in words only: the
 * client never subtracts, so no figure is shown for the difference.
 *
 * @param side The sheet's comparison
 */
@Composable
private fun ComparisonLine(side: RecordSide) {
    val text =
        when (side) {
            RecordSide.INVALID -> return
            RecordSide.EXACT -> stringResource(R.string.verify_line_exact)
            RecordSide.SHORT -> stringResource(R.string.verify_line_short_plain)
            RecordSide.OVER -> stringResource(R.string.verify_line_over_plain)
        }
    Text(
        text,
        style = MaterialTheme.typography.titleSmall,
        color = if (side == RecordSide.EXACT) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
        modifier = Modifier.testTag(TAG_RECORD_LINE),
    )
}
