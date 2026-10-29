package com.shikkhokplus.app.feature.guardian.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.format.shortDate
import com.shikkhokplus.app.core.format.weekdayShort
import com.shikkhokplus.app.core.ui.displayTime
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.guardian.ChildBatch
import com.shikkhokplus.app.feature.guardian.ChildCard
import com.shikkhokplus.app.feature.guardian.GuardianPayment
import com.shikkhokplus.app.feature.guardian.GuardianUiState
import com.shikkhokplus.app.feature.guardian.ResultCard
import com.shikkhokplus.app.feature.guardian.Trend
import com.shikkhokplus.app.feature.guardian.WaitingCard
import com.shikkhokplus.app.feature.pay.PayOption

/** The loading placeholder. */
const val TAG_GUARDIAN_LOADING: String = "guardian_loading"

/** The shown child's name. */
const val TAG_GUARDIAN_SELECTED_NAME: String = "guardian_selected_name"

/** The child switcher, drawn only with more than one child. */
const val TAG_GUARDIAN_SWITCHER: String = "guardian_switcher"

/** One child in the switcher. */
const val TAG_GUARDIAN_CHIP: String = "guardian_chip"

/** The empty state. */
const val TAG_GUARDIAN_EMPTY: String = "guardian_empty"

/** The failure card. */
const val TAG_GUARDIAN_ERROR: String = "guardian_error"

/** The next-payment card's pay button. */
const val TAG_GUARDIAN_PAY: String = "guardian_pay"

/** The link to every payment (G3). */
const val TAG_GUARDIAN_FEES: String = "guardian_fees"

/** One latest result, which opens G2. */
const val TAG_GUARDIAN_RESULT: String = "guardian_result"

/** A payment being checked. */
const val TAG_GUARDIAN_WAITING: String = "guardian_waiting"

/**
 * What the home's buttons do.
 *
 * @property onSelect Show the child at an index
 * @property onPay Pay a fee for the shown child
 * @property onPayments Open the shown child's payments, by one of their seats
 * @property onResult Open a batch's progress, by its seat
 * @property onRetry Read again
 */
data class GuardianActions(
    val onSelect: (Int) -> Unit = {},
    val onPay: (PayOption) -> Unit = {},
    val onPayments: (String) -> Unit = {},
    val onResult: (ResultCard, String) -> Unit = { _, _ -> },
    val onRetry: () -> Unit = {},
)

/**
 * G1: the guardian's home, one child at a time.
 *
 * Every figure is the server's: what to pay next, how late, how a result
 * moved. **Switching child replaces the shown child** [BR4.2] and the
 * screen says so, so one child's marks are never read under another's
 * name.
 *
 * @param state What to render
 * @param actions What the buttons do
 * @param modifier The layout modifier
 * @param bottomBar The navigation bar
 * @param barActions Icons at the bar's end, such as the inbox bell
 */
@Composable
fun GuardianHomeScreen(
    state: GuardianUiState,
    actions: GuardianActions,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
    barActions: @Composable RowScope.() -> Unit = {},
) {
    ScreenScaffold(
        title = stringResource(R.string.guardian_home_title),
        modifier = modifier,
        bottomBar = bottomBar,
        actions = barActions,
    ) {
        when (state) {
            GuardianUiState.Idle -> Unit
            GuardianUiState.Loading -> SkeletonList(modifier = Modifier.testTag(TAG_GUARDIAN_LOADING))
            is GuardianUiState.Empty ->
                EmptyState(
                    title = stringResource(R.string.guardian_none_title),
                    body =
                        state.phone?.let { stringResource(R.string.guardian_none_body, Numerals.phone(it)) }
                            ?: stringResource(R.string.guardian_empty_body),
                    modifier = Modifier.testTag(TAG_GUARDIAN_EMPTY),
                )
            is GuardianUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    modifier = Modifier.testTag(TAG_GUARDIAN_ERROR),
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            is GuardianUiState.Loaded -> Loaded(state, actions)
        }
    }
}

/**
 * The shown child: switcher, who, then payment, results and batches.
 *
 * @param state The loaded state
 * @param actions What the buttons do
 */
@Composable
private fun ColumnScope.Loaded(state: GuardianUiState.Loaded, actions: GuardianActions) {
    val child = state.child
    if (state.children.size > 1) Switcher(state, actions.onSelect)
    Who(child)
    if (state.switched) {
        Text(
            buildAnnotatedString {
                append(stringResource(R.string.guardian_now_showing_before))
                withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(Numerals.freeText(firstName(child.name))) }
                append(stringResource(R.string.guardian_now_showing_after))
            },
            color = Color(0xFFEEF1F5),
            modifier =
                Modifier
                    .fillMaxWidth()
                    .background(Color(0xFF2A2F36), MaterialTheme.shapes.medium)
                    .padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }
    child.payment?.let { PaymentCard(child, it, actions) }
    child.waiting.forEach { WaitingRow(it) }
    if (child.payment == null) {
        TextAction(
            stringResource(R.string.guardian_open_fees),
            { child.batches.firstOrNull()?.let { actions.onPayments(it.enrollmentId) } },
            Modifier.testTag(TAG_GUARDIAN_FEES),
        )
    }
    if (child.results.isNotEmpty()) {
        Section(stringResource(R.string.guardian_latest_results, firstName(child.name)))
        Card {
            child.results.forEachIndexed { index, result ->
                if (index > 0) InsetDivider()
                ResultRow(result) { actions.onResult(result, child.name) }
            }
        }
    }
    if (child.batches.isNotEmpty()) {
        Section(stringResource(R.string.guardian_batches_of, firstName(child.name)))
        Card {
            child.batches.forEachIndexed { index, batch ->
                if (index > 0) InsetDivider()
                BatchRow(batch)
            }
        }
    }
}

/**
 * The pill switcher: one segment per child, the shown one filled.
 *
 * @param state The loaded state
 * @param onSelect Called with a child's index
 */
@Composable
private fun Switcher(state: GuardianUiState.Loaded, onSelect: (Int) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceContainerHigh, RoundedCornerShape(30.dp))
            .padding(4.dp)
            .testTag(TAG_GUARDIAN_SWITCHER),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        state.children.forEachIndexed { index, child ->
            val on = index == state.selected
            Row(
                Modifier
                    .weight(1f)
                    .heightIn(min = 52.dp)
                    .background(
                        if (on) MaterialTheme.colorScheme.primary else Color.Transparent,
                        RoundedCornerShape(26.dp),
                    )
                    .clickable { onSelect(index) }
                    .testTag(TAG_GUARDIAN_CHIP),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Initial(child.name, size = 30, inverted = on)
                Text(
                    Numerals.freeText(firstName(child.name)),
                    modifier = Modifier.padding(start = 8.dp),
                    style =
                        MaterialTheme.typography.titleMedium.copy(
                            fontWeight = if (on) FontWeight.Bold else FontWeight.SemiBold,
                        ),
                    color = if (on) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/**
 * The shown child's initial, name and batch count.
 *
 * @param child The child
 */
@Composable
private fun Who(child: ChildCard) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Initial(child.name, size = 48, inverted = false, filled = true)
        Column {
            Text(
                Numerals.freeText(child.name),
                style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold),
                modifier = Modifier.testTag(TAG_GUARDIAN_SELECTED_NAME),
            )
            Text(
                if (child.batchCount == 1) {
                    stringResource(R.string.guardian_one_batch)
                } else {
                    stringResource(R.string.guardian_batch_count, Numerals.count(child.batchCount))
                },
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * A round initial.
 *
 * @param name Whose
 * @param size Its diameter in dp
 * @param inverted White on the primary pill, primary text on white
 * @param filled A primary disc with white text, as the header draws it
 */
@Composable
private fun Initial(name: String, size: Int, inverted: Boolean, filled: Boolean = false) {
    Box(
        Modifier
            .size(size.dp)
            .background(if (filled) MaterialTheme.colorScheme.primary else Color.White, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            name.trim().take(1),
            style =
                if (filled) MaterialTheme.typography.titleLarge else MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
            color =
                when {
                    filled -> MaterialTheme.colorScheme.onPrimary
                    inverted -> MaterialTheme.colorScheme.primary
                    else -> MaterialTheme.colorScheme.onSurfaceVariant
                },
        )
    }
}

/**
 * "Tasnim's next payment": the amount, what for and by when, and Pay.
 *
 * @param child The child
 * @param payment The fee the server chose
 * @param actions What the buttons do
 */
@Composable
private fun PaymentCard(child: ChildCard, payment: GuardianPayment, actions: GuardianActions) {
    val option = payment.option
    Card(Modifier.padding(horizontal = 16.dp, vertical = 14.dp), spacing = 6.dp) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                stringResource(R.string.guardian_next_payment, Numerals.freeText(firstName(child.name))),
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f),
            )
            payment.daysLate?.let {
                PaymentStateChip(
                    PaymentState.OVERDUE,
                    stringResource(R.string.guardian_days_late, Numerals.count(it)),
                    compact = true,
                )
            }
        }
        Text(
            Numerals.money(option.amountDue),
            style = MaterialTheme.typography.displaySmall.copy(fontWeight = FontWeight.Bold),
        )
        Text(
            buildAnnotatedString {
                append(Numerals.freeText(option.batchName))
                append(" · ")
                append(monthName(option.period, short = false))
                option.dueDate?.takeIf { payment.daysLate == null }?.let {
                    append(" · ")
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold)) {
                        append(stringResource(R.string.guardian_due_on, shortDate(it)))
                    }
                }
            },
            style = MaterialTheme.typography.bodyLarge,
        )
        if (payment.laterPeriods > 0) {
            Text(
                stringResource(
                    R.string.guardian_more_owed,
                    Numerals.count(payment.laterPeriods),
                    Numerals.money(payment.totalDue),
                ),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        PrimaryButton(
            text = stringResource(R.string.guardian_pay_amount, Numerals.money(option.amountDue)),
            onClick = { actions.onPay(option) },
            modifier = Modifier.fillMaxWidth().padding(top = 6.dp).testTag(TAG_GUARDIAN_PAY),
        )
        TextAction(
            stringResource(R.string.guardian_open_fees),
            { actions.onPayments(option.enrollmentId) },
            Modifier.align(Alignment.CenterHorizontally).testTag(TAG_GUARDIAN_FEES),
        )
    }
}

/**
 * A payment sent and being checked.
 *
 * @param waiting The payment
 */
@Composable
private fun WaitingRow(waiting: WaitingCard) {
    Card(Modifier.padding(horizontal = 16.dp, vertical = 12.dp).testTag(TAG_GUARDIAN_WAITING)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    listOfNotNull(
                        Numerals.freeText(waiting.batchName),
                        monthName(waiting.period, short = false) +
                            (waiting.amount?.let { " " + Numerals.money(it) } ?: ""),
                    ).joinToString(" · "),
                    style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
                )
                waiting.sentAt?.let {
                    Quiet(stringResource(R.string.guardian_sent_checking, shortDate(it.take(DATE_LENGTH))))
                }
            }
            PaymentStateChip(PaymentState.VERIFYING, stringResource(R.string.student_chip_verifying), compact = true)
        }
    }
}

/**
 * One batch's latest result, with how it moved.
 *
 * @param result The result
 * @param onOpen Called to open G2
 */
@Composable
private fun ResultRow(result: ResultCard, onOpen: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onOpen)
            .heightIn(min = 64.dp)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .testTag(TAG_GUARDIAN_RESULT),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(Numerals.freeText(result.batchName), style = MaterialTheme.typography.titleMedium)
            Quiet("${Numerals.freeText(result.title)} · ${shortDate(result.date)}")
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(
                buildAnnotatedString {
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold, fontSize = 21.sp)) {
                        append(Numerals.count(result.marks))
                    }
                    withStyle(SpanStyle(color = Color.Unspecified)) { append("/" + Numerals.count(result.totalMarks)) }
                },
            )
            Quiet(trendLine(result))
        }
    }
}

/**
 * "up from 39", "down from 64", "same as last" or "first test".
 *
 * @param result The result
 * @return The line
 */
@Composable
private fun trendLine(result: ResultCard): String {
    val previous = result.previousMarks?.let(Numerals::count).orEmpty()
    return when (result.trend) {
        Trend.UP -> stringResource(R.string.guardian_up_from, previous)
        Trend.DOWN -> stringResource(R.string.guardian_down_from, previous)
        Trend.SAME -> stringResource(R.string.guardian_same_as_last)
        Trend.FIRST -> stringResource(R.string.guardian_first_test)
    }
}

/**
 * One batch: name, then teacher and the next class.
 *
 * @param batch The batch
 */
@Composable
private fun BatchRow(batch: ChildBatch) {
    Column(Modifier.fillMaxWidth().heightIn(min = 64.dp).padding(horizontal = 16.dp, vertical = 12.dp)) {
        Text(Numerals.freeText(batch.batchName), style = MaterialTheme.typography.titleMedium)
        val next = batch.next
        val upcoming =
            when {
                next == null -> null
                next.startsInMinutes != null && next.moved ->
                    stringResource(R.string.guardian_today_moved, displayTime(next.startTime))
                next.startsInMinutes != null -> stringResource(
                    R.string.guardian_next_today,
                    displayTime(next.startTime),
                )
                else -> stringResource(R.string.guardian_next_on, weekdayShort(next.date), displayTime(next.startTime))
            }
        val line = listOfNotNull(batch.teacherName?.let(Numerals::freeText), upcoming).joinToString(" · ")
        if (line.isNotEmpty()) Quiet(line)
    }
}

/**
 * A section heading.
 *
 * @param text The heading
 */
@Composable
private fun Section(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(top = 4.dp),
    )
}

/**
 * A quiet secondary line.
 *
 * @param text The line
 */
@Composable
private fun Quiet(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/**
 * A white card.
 *
 * @param modifier Inner padding and tags
 * @param spacing The gap between its children; none for a list of rows
 * @param content The card's contents
 */
@Composable
private fun Card(
    modifier: Modifier = Modifier,
    spacing: Dp = 0.dp,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .then(modifier),
        verticalArrangement = Arrangement.spacedBy(spacing),
        content = content,
    )
}

/** The divider between rows, inset as the boards draw it. */
@Composable
private fun InsetDivider() {
    HorizontalDivider(Modifier.padding(start = 16.dp), color = MaterialTheme.colorScheme.surfaceContainerHigh)
}

/**
 * The first word of a name, as the board's headings use it ("তাসনিম's").
 *
 * @param name The full name
 * @return Its first word
 */
fun firstName(name: String): String = name.trim().substringBefore(" ")

/** `yyyy-MM-dd` out of a timestamp. */
private const val DATE_LENGTH = 10
