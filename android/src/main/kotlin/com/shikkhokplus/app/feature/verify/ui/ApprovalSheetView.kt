package com.shikkhokplus.app.feature.verify.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.verify.AmountSide
import com.shikkhokplus.app.feature.verify.ApprovalSheet
import com.shikkhokplus.app.feature.verify.REVIEW_NOTE_MAX

/** The amount received field. */
const val TAG_SHEET_AMOUNT: String = "sheet_amount"

/** The carry-forward option. */
const val TAG_SHEET_CARRY: String = "sheet_carry"

/** The waive option. */
const val TAG_SHEET_WAIVE: String = "sheet_waive"

/** One child in the picker; the child's seat id follows an underscore. */
const val TAG_SHEET_CHILD: String = "sheet_child"

/** The sheet's approve button. */
const val TAG_SHEET_CONFIRM: String = "sheet_confirm"

/** The sheet's note field. */
const val TAG_SHEET_NOTE: String = "sheet_note"

/** The line saying how the amount compares. */
const val TAG_SHEET_LINE: String = "sheet_line"

private const val CARRIED = "carried"
private const val WAIVED = "waived"

/**
 * What the approval sheet can do.
 *
 * @property onType The amount received, as typed
 * @property onDisposition `carried` or `waived`
 * @property onChild A child's seat id
 * @property onNote The note to the family
 * @property onConfirm Send the approval
 * @property onDismiss Close without deciding
 */
class SheetActions(
    val onType: (String) -> Unit,
    val onDisposition: (String) -> Unit,
    val onChild: (String) -> Unit,
    val onNote: (String) -> Unit,
    val onConfirm: () -> Unit,
    val onDismiss: () -> Unit,
)

/**
 * R4: approve a payment for the amount actually received.
 *
 * **Which controls appear is a display choice**, from comparing the
 * typed amount with what the server says is owed together; the server
 * re-checks every choice. Carry or waive appears only when short; a
 * child is asked for only when several are covered and the amount is
 * not exact.
 *
 * @param sheet The sheet's state
 * @param busy Whether the approval is being sent
 * @param errorKey A failed write's message key, if any
 * @param actions What the sheet can do
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ApprovalSheetView(
    sheet: ApprovalSheet,
    busy: Boolean,
    errorKey: String?,
    actions: SheetActions,
) {
    val card = sheet.card
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
            Text(stringResource(R.string.verify_sheet_title), style = MaterialTheme.typography.titleLarge)
            Text(
                stringResource(R.string.verify_sheet_sub, Numerals.freeText(card.batchName)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            errorKey?.let {
                Banner(title = stringResource(MessageKeys.resolve(it)), tone = BannerTone.ERROR)
            }
            card.children.forEach { child ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(
                        stringResource(
                            R.string.verify_child_line,
                            Numerals.freeText(child.displayName),
                            monthName(child.period, short = false),
                        ),
                        style = BodyCompact,
                    )
                    Text(Numerals.money(child.owed), style = BodyCompact)
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(stringResource(R.string.verify_owed_together), style = MaterialTheme.typography.titleSmall)
                Text(Numerals.money(card.owedTogether), style = MaterialTheme.typography.titleSmall)
            }
            ShikkhokTextField(
                value = sheet.typed,
                onValueChange = actions.onType,
                label = stringResource(R.string.verify_received_amount),
                prefix = "৳",
                error = stringResource(R.string.fee_invalid).takeIf { received == null && sheet.typed.isNotEmpty() },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                fieldModifier = Modifier.testTag(TAG_SHEET_AMOUNT),
            )
            ComparisonLine(sheet)
            if (sheet.needsDisposition) Disposition(sheet, actions)
            if (sheet.needsChild) ChildPicker(sheet, actions)
            ShikkhokTextField(
                value = sheet.note,
                onValueChange = { actions.onNote(it.take(REVIEW_NOTE_MAX)) },
                label = stringResource(R.string.verify_note_to_them),
                singleLine = false,
                minLines = 2,
                fieldModifier = Modifier.testTag(TAG_SHEET_NOTE),
            )
            PrimaryButton(
                text =
                    stringResource(
                        R.string.verify_partial_confirm,
                        received?.let(Numerals::money) ?: sheet.typed,
                    ),
                onClick = actions.onConfirm,
                enabled = sheet.canConfirm && !busy,
                modifier = Modifier.fillMaxWidth().testTag(TAG_SHEET_CONFIRM),
            )
            TextAction(stringResource(R.string.action_cancel), actions.onDismiss, Modifier.fillMaxWidth())
        }
    }
}

/**
 * How the typed amount stands against what is owed.
 *
 * The figure shown is the server's difference, and only while the amount
 * is the one the payer reported; for any other amount the line says
 * which side it falls on, since the client never subtracts.
 *
 * @param sheet The sheet's state
 */
@Composable
private fun ComparisonLine(sheet: ApprovalSheet) {
    val difference = sheet.shownDifference?.let(Numerals::money)
    val text =
        when (sheet.side) {
            AmountSide.INVALID -> return
            AmountSide.EXACT -> stringResource(R.string.verify_line_exact)
            AmountSide.SHORT ->
                difference?.let { stringResource(R.string.verify_line_short, it) }
                    ?: stringResource(R.string.verify_line_short_plain)
            AmountSide.OVER ->
                difference?.let { stringResource(R.string.verify_line_over, it) }
                    ?: stringResource(R.string.verify_line_over_plain)
        }
    Text(
        text,
        style = MaterialTheme.typography.titleSmall,
        color =
            if (sheet.side == AmountSide.EXACT) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
        modifier = Modifier.testTag(TAG_SHEET_LINE),
    )
}

/**
 * Carry forward or waive, for a short payment.
 *
 * @param sheet The sheet's state
 * @param actions What the sheet can do
 */
@Composable
private fun Disposition(sheet: ApprovalSheet, actions: SheetActions) {
    Option(
        title = stringResource(R.string.verify_carry_forward),
        body = stringResource(R.string.verify_carry_forward_body),
        selected = sheet.disposition == CARRIED,
        onSelect = { actions.onDisposition(CARRIED) },
        modifier = Modifier.testTag(TAG_SHEET_CARRY),
    )
    Option(
        title = stringResource(R.string.verify_waive),
        body = stringResource(R.string.verify_waive_body),
        selected = sheet.disposition == WAIVED,
        onSelect = { actions.onDisposition(WAIVED) },
        modifier = Modifier.testTag(TAG_SHEET_WAIVE),
    )
}

/**
 * Which child takes the shortfall, or gets the credit.
 *
 * Each option notes the other children as marked paid, which is copy
 * naming them and not a figure.
 *
 * @param sheet The sheet's state
 * @param actions What the sheet can do
 */
@Composable
private fun ChildPicker(sheet: ApprovalSheet, actions: SheetActions) {
    val difference = sheet.shownDifference?.let(Numerals::money)
    val heading =
        when {
            sheet.side == AmountSide.OVER -> stringResource(R.string.verify_credit_to)
            sheet.disposition == WAIVED -> stringResource(R.string.verify_waive_for)
            difference != null -> stringResource(R.string.verify_carry_onto, difference)
            else -> stringResource(R.string.verify_carry_onto_plain)
        }
    Text(heading, style = MaterialTheme.typography.titleMedium)
    sheet.card.children.forEach { child ->
        val others =
            sheet.card.children
                .filter { it.enrollmentId != child.enrollmentId }
                .joinToString(", ") { Numerals.freeText(it.displayName) }
        Option(
            title = Numerals.freeText(child.displayName),
            body = stringResource(R.string.verify_marked_paid, others),
            selected = sheet.childId == child.enrollmentId,
            onSelect = { actions.onChild(child.enrollmentId) },
            modifier = Modifier.testTag("${TAG_SHEET_CHILD}_${child.enrollmentId}"),
        )
    }
}

/**
 * One choice, as a bordered card with a radio button.
 *
 * @param title The choice
 * @param body What it means
 * @param selected Whether it is chosen
 * @param onSelect Called to choose it
 * @param modifier The layout modifier
 */
@Composable
private fun Option(
    title: String,
    body: String,
    selected: Boolean,
    onSelect: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = MaterialTheme.colorScheme
    Row(
        modifier
            .fillMaxWidth()
            .border(
                width = if (selected) 2.dp else 1.5.dp,
                color = if (selected) colors.primary else colors.outlineVariant,
                shape = MaterialTheme.shapes.medium,
            )
            .selectable(selected = selected, onClick = onSelect, role = Role.RadioButton)
            .padding(14.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        RadioButton(selected = selected, onClick = null)
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(body, style = BodyCompact, color = colors.onSurfaceVariant)
        }
    }
}
