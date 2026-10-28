package com.shikkhokplus.app.feature.verify.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
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
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.verify.PartialSheet

/** The amount field. */
const val TAG_PARTIAL_AMOUNT: String = "partial_amount"

/** The carry-forward option. */
const val TAG_PARTIAL_CARRY: String = "partial_carry"

/** The waive option. */
const val TAG_PARTIAL_WAIVE: String = "partial_waive"

/** The approve button. */
const val TAG_PARTIAL_CONFIRM: String = "partial_confirm"

/** The disposition value the server reads for carrying forward. */
private const val CARRIED = "carried"

/** The disposition value the server reads for waiving. */
private const val WAIVED = "waived"

/**
 * Approve part of a payment, and say what happens to the rest (T4).
 *
 * **The shortfall is the server's answer for the typed amount**, not a
 * subtraction here [BR5.3]. Until it answers, the carry and waive
 * options are not shown and approving is not offered, so the teacher
 * never confirms against a figure the server has not stated.
 *
 * @param sheet The sheet's state
 * @param onType Called with the amount as typed
 * @param onChoose Called with `carried` or `waived`
 * @param onConfirm Called to approve
 * @param onDismiss Called to close without deciding
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PartialApprovalSheet(
    sheet: PartialSheet,
    onType: (String) -> Unit,
    onChoose: (String) -> Unit,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    val card = sheet.card
    val amount = Money.fromTyped(sheet.typed)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = MaterialTheme.colorScheme.surface,
    ) {
        Column(
            Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(
                stringResource(
                    R.string.verify_partial_title,
                    amount?.let(Numerals::money) ?: sheet.typed,
                    Numerals.money(card.charged),
                ),
                style = MaterialTheme.typography.titleLarge,
            )
            Text(
                stringResource(
                    R.string.verify_partial_sub,
                    Numerals.freeText(card.displayName),
                    monthName(card.period, short = false),
                    card.channel,
                ),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            ShikkhokTextField(
                value = sheet.typed,
                onValueChange = onType,
                label = stringResource(R.string.verify_partial_amount),
                prefix = "৳",
                error = stringResource(R.string.fee_invalid).takeIf { amount == null && sheet.typed.isNotEmpty() },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                fieldModifier = Modifier.testTag(TAG_PARTIAL_AMOUNT),
            )
            val shortfall = sheet.shortfall
            if (shortfall != null && sheet.dispositionRequired) {
                val short = Numerals.money(shortfall)
                Text(
                    stringResource(R.string.verify_partial_question, short),
                    style = MaterialTheme.typography.titleMedium,
                )
                Option(
                    title = stringResource(R.string.verify_carry, short),
                    body = stringResource(R.string.verify_carry_body),
                    selected = sheet.disposition == CARRIED,
                    onSelect = { onChoose(CARRIED) },
                    modifier = Modifier.testTag(TAG_PARTIAL_CARRY),
                )
                Option(
                    title = stringResource(R.string.verify_waive, short),
                    body = stringResource(R.string.verify_waive_body),
                    selected = sheet.disposition == WAIVED,
                    onSelect = { onChoose(WAIVED) },
                    modifier = Modifier.testTag(TAG_PARTIAL_WAIVE),
                )
            }
            PrimaryButton(
                text = confirmLabel(sheet, amount),
                onClick = onConfirm,
                enabled =
                    amount != null &&
                        shortfall != null &&
                        (!sheet.dispositionRequired || sheet.disposition != null),
                modifier = Modifier.fillMaxWidth().testTag(TAG_PARTIAL_CONFIRM),
            )
            TextAction(stringResource(R.string.action_cancel), onDismiss, Modifier.fillMaxWidth())
        }
    }
}

/**
 * The approve button's words, naming what will happen.
 *
 * @param sheet The sheet's state
 * @param amount The typed amount, or null
 * @return The label
 */
@Composable
private fun confirmLabel(sheet: PartialSheet, amount: Money?): String {
    val approved = amount?.let(Numerals::money) ?: sheet.typed
    val short = sheet.shortfall?.let(Numerals::money)
    return when {
        short == null || !sheet.dispositionRequired -> stringResource(R.string.verify_partial_confirm, approved)
        sheet.disposition == CARRIED -> stringResource(R.string.verify_partial_confirm_carry, approved, short)
        sheet.disposition == WAIVED -> stringResource(R.string.verify_partial_confirm_waive, approved, short)
        else -> stringResource(R.string.verify_partial_confirm, approved)
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
