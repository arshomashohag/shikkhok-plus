package com.shikkhokplus.app.feature.extrafees.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
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
import com.shikkhokplus.app.core.format.isoDate
import com.shikkhokplus.app.core.format.isoToUtcMillis
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.network.ExtraFeeDetailDto
import com.shikkhokplus.app.core.network.ExtraFeeStudentDto
import com.shikkhokplus.app.core.network.ExtraFeeSummaryDto
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.extrafees.ExtraFeeDetailUiState
import com.shikkhokplus.app.feature.extrafees.ExtraFeesUiState
import com.shikkhokplus.app.feature.extrafees.FeeKind
import com.shikkhokplus.app.feature.extrafees.RaiseFeeUiState
import com.shikkhokplus.app.feature.extrafees.SeatChoice

/** The raise-a-fee action on the list. */
const val TAG_EXTRA_FEES_RAISE: String = "extra_fees_raise"

/** The list's empty state. */
const val TAG_EXTRA_FEES_EMPTY: String = "extra_fees_empty"

/** The raise form's name field. */
const val TAG_RAISE_LABEL: String = "raise_label"

/** The raise form's amount field. */
const val TAG_RAISE_AMOUNT: String = "raise_amount"

/** The raise form's send button. */
const val TAG_RAISE_SUBMIT: String = "raise_submit"

/** The raise form's refusal. */
const val TAG_RAISE_FAILURE: String = "raise_failure"

/**
 * Tag for one fee on the list.
 *
 * @param extraFeeId The fee
 * @return The tag
 */
fun extraFeeTag(extraFeeId: String): String = "extra_fee_$extraFeeId"

/**
 * Tag for one student's choice chip on the raise form.
 *
 * @param enrollmentId The seat
 * @param choice The choice
 * @return The tag
 */
fun seatChoiceTag(enrollmentId: String, choice: SeatChoice): String = "raise_seat_${enrollmentId}_${choice.name}"

/**
 * Tag for one student's record action on a fee.
 *
 * @param enrollmentId The seat
 * @return The tag
 */
fun feeRecordTag(enrollmentId: String): String = "fee_record_$enrollmentId"

/**
 * A batch's exam and other fees, newest first, each with the server's
 * collected-of-charged line and who still owes.
 *
 * @param state What to render
 * @param onOpen Opens one fee
 * @param onRaise Opens the raise form
 * @param onRetry Reads again after a failure
 * @param onBack Leaves the screen
 * @param modifier Layout modifier from the caller
 */
@Composable
fun ExtraFeesScreen(
    state: ExtraFeesUiState,
    onOpen: (String) -> Unit,
    onRaise: () -> Unit,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.extra_fees_title), modifier = modifier, onBack = onBack) {
        when (state) {
            ExtraFeesUiState.Loading -> SkeletonList(rows = 3)
            is ExtraFeesUiState.Loaded ->
                if (state.fees.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.extra_fees_title),
                        body = stringResource(R.string.extra_fees_empty),
                        modifier = Modifier.testTag(TAG_EXTRA_FEES_EMPTY),
                    )
                } else {
                    state.fees.forEach { fee -> FeeCard(fee) { onOpen(fee.extraFeeId) } }
                }
            is ExtraFeesUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = stringResource(R.string.extra_fees_load_failed),
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) onRetry else null,
                )
        }
        if (state != ExtraFeesUiState.Loading) {
            PrimaryButton(
                text = stringResource(R.string.extra_fees_raise),
                onClick = onRaise,
                modifier = Modifier.fillMaxWidth().testTag(TAG_EXTRA_FEES_RAISE),
            )
        }
    }
}

@Composable
private fun FeeCard(fee: ExtraFeeSummaryDto, onOpen: () -> Unit) {
    ShikkhokCard(modifier = Modifier.testTag(extraFeeTag(fee.extraFeeId)), onClick = onOpen) {
        Text(Numerals.freeText(fee.label), style = MaterialTheme.typography.titleMedium)
        Text(
            text = kindLine(FeeKind.fromWire(fee.purpose), fee.dueOn, fee.examTitle),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text =
                if (fee.owingCount == 0) {
                    stringResource(R.string.extra_fees_fully_paid)
                } else {
                    stringResource(
                        R.string.extra_fees_counts,
                        Numerals.count(fee.paidCount),
                        Numerals.count(fee.studentCount),
                        Numerals.count(fee.owingCount),
                        Numerals.money(fee.owedTotal),
                    )
                },
            style = MaterialTheme.typography.bodyMedium,
        )
        Text(
            text =
                stringResource(
                    R.string.extra_fees_collected,
                    Numerals.money(fee.collectedTotal),
                    Numerals.money(fee.chargedTotal),
                ),
            style = MaterialTheme.typography.titleSmall,
        )
    }
}

@Composable
private fun kindLine(kind: FeeKind, dueOn: String, examTitle: String?): String =
    listOfNotNull(
        stringResource(kindLabel(kind)),
        stringResource(R.string.extra_fees_due, shortDate(dueOn)),
        examTitle?.let { stringResource(R.string.extra_fees_for_exam, Numerals.freeText(it)) },
    ).joinToString(" · ")

/**
 * What the raise form's controls call.
 *
 * @property onKind Chooses exam or other
 * @property onLabel Edits the name
 * @property onExam Links an exam, or none
 * @property onAmount Edits the amount per student
 * @property onDueOn Picks the due date
 * @property onChoose Charges, waives or leaves out one student
 * @property onRaise Sends the form
 * @property onRetry Reads the students again
 * @property onCancel Leaves without raising
 */
data class RaiseFeeActions(
    val onKind: (FeeKind) -> Unit = {},
    val onLabel: (String) -> Unit = {},
    val onExam: (String?) -> Unit = {},
    val onAmount: (String) -> Unit = {},
    val onDueOn: (String) -> Unit = {},
    val onChoose: (String, SeatChoice) -> Unit = { _, _ -> },
    val onRaise: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onCancel: () -> Unit = {},
)

/**
 * Raise an exam or other fee on a batch: its kind, name, linked exam,
 * amount per student and due date, and per student whether to charge,
 * waive or leave them out. The server checks every value.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@OptIn(ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
fun RaiseFeeScreen(
    state: RaiseFeeUiState,
    actions: RaiseFeeActions,
    modifier: Modifier = Modifier,
) {
    var picking by remember { mutableStateOf(false) }
    ScreenScaffold(
        title = stringResource(R.string.extra_fees_form_title),
        modifier = modifier,
        onBack = actions.onCancel,
    ) {
        if (state.loading) {
            SkeletonList(rows = 4)
            return@ScreenScaffold
        }
        state.loadFailedKey?.let {
            ErrorCard(
                title = stringResource(MessageKeys.resolve(it)),
                body = stringResource(R.string.extra_fees_load_failed),
                retryLabel = stringResource(R.string.auth_retry),
                onRetry = actions.onRetry,
            )
            return@ScreenScaffold
        }
        Text(stringResource(R.string.extra_fees_form_kind), style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FeeKind.entries.forEach { kind ->
                FilterChip(
                    selected = state.kind == kind,
                    onClick = { actions.onKind(kind) },
                    label = { Text(stringResource(kindLabel(kind))) },
                )
            }
        }
        ShikkhokTextField(
            value = state.label,
            onValueChange = actions.onLabel,
            label = stringResource(R.string.extra_fees_form_label),
            fieldModifier = Modifier.testTag(TAG_RAISE_LABEL),
        )
        if (state.kind == FeeKind.EXAM && state.exams.isNotEmpty()) {
            Text(stringResource(R.string.extra_fees_form_exam), style = MaterialTheme.typography.labelLarge)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(
                    selected = state.examId == null,
                    onClick = { actions.onExam(null) },
                    label = { Text(stringResource(R.string.extra_fees_form_no_exam)) },
                )
                state.exams.forEach { exam ->
                    FilterChip(
                        selected = state.examId == exam.examId,
                        onClick = { actions.onExam(exam.examId) },
                        label = { Text(Numerals.freeText(exam.title)) },
                    )
                }
            }
        }
        ShikkhokTextField(
            value = state.typedAmount,
            onValueChange = actions.onAmount,
            label = stringResource(R.string.extra_fees_form_amount),
            prefix = "৳",
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            fieldModifier = Modifier.testTag(TAG_RAISE_AMOUNT),
        )
        Text(stringResource(R.string.extra_fees_form_due), style = MaterialTheme.typography.labelLarge)
        SecondaryButton(text = shortDate(state.dueOn), onClick = { picking = true }, modifier = Modifier.fillMaxWidth())
        Text(stringResource(R.string.extra_fees_form_students), style = MaterialTheme.typography.labelLarge)
        state.students.forEach { student ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(Numerals.freeText(student.name), style = MaterialTheme.typography.bodyLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SeatChoice.entries.forEach { choice ->
                        FilterChip(
                            selected = state.choiceOf(student.enrollmentId) == choice,
                            onClick = { actions.onChoose(student.enrollmentId, choice) },
                            label = { Text(stringResource(choiceLabel(choice))) },
                            modifier = Modifier.testTag(seatChoiceTag(student.enrollmentId, choice)),
                        )
                    }
                }
            }
        }
        Text(
            text = stringResource(R.string.extra_fees_form_note),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        state.failureKey?.let {
            Banner(
                title = stringResource(MessageKeys.resolve(it)),
                tone = BannerTone.ERROR,
                modifier = Modifier.testTag(TAG_RAISE_FAILURE),
            )
        }
        PrimaryButton(
            text = stringResource(R.string.extra_fees_raise_for, Numerals.count(state.chargedCount)),
            onClick = actions.onRaise,
            enabled = state.canRaise,
            modifier = Modifier.fillMaxWidth().testTag(TAG_RAISE_SUBMIT),
        )
        SecondaryButton(
            text = stringResource(R.string.action_cancel),
            onClick = actions.onCancel,
            modifier = Modifier.fillMaxWidth(),
        )
    }
    if (picking) {
        val picker = rememberDatePickerState(initialSelectedDateMillis = isoToUtcMillis(state.dueOn))
        DatePickerDialog(
            onDismissRequest = { picking = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        picker.selectedDateMillis?.let { actions.onDueOn(isoDate(it)) }
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

private fun kindLabel(kind: FeeKind): Int =
    if (kind == FeeKind.EXAM) R.string.extra_fees_kind_exam else R.string.extra_fees_kind_other

private fun choiceLabel(choice: SeatChoice): Int =
    when (choice) {
        SeatChoice.CHARGE -> R.string.extra_fees_form_charge
        SeatChoice.WAIVE -> R.string.extra_fees_form_waive
        SeatChoice.LEAVE_OUT -> R.string.extra_fees_form_leave_out
    }

/**
 * One fee: the server's collected-of-charged line and each student's
 * paid and owed, with "Record payment" for a student who still owes.
 *
 * @param state What to render
 * @param recorded Whether a record was just accepted
 * @param onRecord Opens the record sheet for one student
 * @param onRetry Reads again after a failure
 * @param onBack Leaves the screen
 * @param modifier Layout modifier from the caller
 */
@Composable
fun ExtraFeeDetailScreen(
    state: ExtraFeeDetailUiState,
    recorded: Boolean,
    onRecord: (ExtraFeeStudentDto) -> Unit,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val fee = (state as? ExtraFeeDetailUiState.Loaded)?.fee
    ScreenScaffold(
        title = fee?.let { Numerals.freeText(it.label) } ?: stringResource(R.string.extra_fees_title),
        subtitle = fee?.let { stringResource(R.string.extra_fees_due, shortDate(it.dueOn)) },
        modifier = modifier,
        onBack = onBack,
    ) {
        if (recorded) {
            Banner(title = stringResource(R.string.fees_record_done), tone = BannerTone.INFO)
        }
        when (state) {
            ExtraFeeDetailUiState.Loading -> SkeletonList(rows = 4)
            is ExtraFeeDetailUiState.Loaded -> FeeDetail(state.fee, onRecord)
            is ExtraFeeDetailUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = stringResource(R.string.extra_fees_load_failed),
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) onRetry else null,
                )
        }
    }
}

@Composable
private fun FeeDetail(fee: ExtraFeeDetailDto, onRecord: (ExtraFeeStudentDto) -> Unit) {
    ShikkhokCard {
        Text(
            text =
                stringResource(
                    R.string.extra_fees_collected,
                    Numerals.money(fee.collectedTotal),
                    Numerals.money(fee.chargedTotal),
                ),
            style = MaterialTheme.typography.headlineSmall,
        )
        fee.examTitle?.let {
            Text(
                text = stringResource(R.string.extra_fees_for_exam, Numerals.freeText(it)),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
    fee.students.forEach { student ->
        ShikkhokCard {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(Numerals.freeText(student.displayName), style = MaterialTheme.typography.titleMedium)
                    Text(
                        text =
                            stringResource(
                                R.string.extra_fees_student_line,
                                Numerals.money(student.paid),
                                Numerals.money(student.owed),
                            ),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(stringResource(statusLabel(student.status)), style = MaterialTheme.typography.labelLarge)
            }
            // The server's status decides whether anything is owed: a
            // paid or waived charge offers nothing to record.
            if (student.status == "unpaid" || student.status == "partly_paid") {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextAction(
                        text = stringResource(R.string.extra_fees_record_payment),
                        onClick = { onRecord(student) },
                        modifier = Modifier.testTag(feeRecordTag(student.enrollmentId)),
                    )
                }
            }
        }
    }
}

private fun statusLabel(status: String): Int =
    when (status) {
        "paid" -> R.string.fees_status_paid
        "partly_paid" -> R.string.fees_status_partly_paid
        "waived" -> R.string.fees_status_waived
        else -> R.string.fees_status_unpaid
    }
