package com.shikkhokplus.app.feature.dues.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.PaymentState
import com.shikkhokplus.app.core.designsystem.PaymentStateChip
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.dues.DuesBatch
import com.shikkhokplus.app.feature.dues.DuesFilter
import com.shikkhokplus.app.feature.dues.DuesGroupKind
import com.shikkhokplus.app.feature.dues.DuesGroupTotal
import com.shikkhokplus.app.feature.dues.DuesRow
import com.shikkhokplus.app.feature.dues.DuesSummary
import com.shikkhokplus.app.feature.dues.DuesUiState
import com.shikkhokplus.app.feature.dues.RemindState

/** Stable test identifiers. Not user-visible text. */
const val TAG_DUES_LOADING: String = "dues_loading"

/** The good-news empty state: nobody owes anything. */
const val TAG_DUES_EMPTY: String = "dues_empty"

/** The list of people who owe. */
const val TAG_DUES_LIST: String = "dues_list"

/** One person who owes. */
const val TAG_DUES_ROW: String = "dues_row"

/** The amount on one row. */
const val TAG_DUES_AMOUNT: String = "dues_amount"

/** The days-late chip on one row. */
const val TAG_DUES_DAYS: String = "dues_days"

/** The headline card. */
const val TAG_DUES_SUMMARY: String = "dues_summary"

/** A group's heading. */
const val TAG_DUES_GROUP: String = "dues_group"

/** One filter chip. */
const val TAG_DUES_FILTER: String = "dues_filter"

/** The error message. */
const val TAG_DUES_ERROR: String = "dues_error"

/** The retry button, shown only when the server said retryable. */
const val TAG_DUES_RETRY: String = "dues_retry"

/** The "Remind N late students" button. */
const val TAG_DUES_REMIND: String = "dues_remind"

/** The confirmation's send button. */
const val TAG_DUES_REMIND_SEND: String = "dues_remind_send"

/** The result of a reminder. */
const val TAG_DUES_REMIND_RESULT: String = "dues_remind_result"

/**
 * What the screen's buttons do.
 *
 * @property onRetry Load again after a failure
 * @property onFilter Open a filter
 * @property onNarrow Narrow to a batch, or null for all
 * @property onAskRemind Ask to confirm a reminder
 * @property onRemind Send it
 * @property onDismissRemind Close the confirmation or its result
 */
data class DuesActions(
    val onRetry: () -> Unit = {},
    val onFilter: (DuesFilter) -> Unit = {},
    val onNarrow: (DuesBatch?) -> Unit = {},
    val onAskRemind: () -> Unit = {},
    val onRemind: () -> Unit = {},
    val onDismissRemind: () -> Unit = {},
)

/**
 * T5: everyone who owes this teacher money, across every batch [FR7.1].
 *
 * **No composable here compares a domain value.** The server decided
 * who appears, in what order, how late each is, which group it is in,
 * every total and every share of the bar, and who a reminder would
 * reach; this renders what it was given [TC-9, D-31].
 *
 * @param state What to render
 * @param actions What the buttons do
 * @param modifier The layout modifier
 * @param bottomBar The navigation bar, supplied by the route so this
 *   screen stays renderable in a test without one
 */
@Composable
fun DuesScreen(
    state: DuesUiState,
    actions: DuesActions,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
) {
    ListScreenScaffold(
        title = stringResource(R.string.dues_title),
        modifier = modifier,
        bottomBar = {
            Column {
                if (state is DuesUiState.Loaded && state.summary.remindable > 0) {
                    RemindBar(state.summary.remindable, state.remind == RemindState.Sending, actions.onAskRemind)
                }
                bottomBar()
            }
        },
    ) {
        when (state) {
            DuesUiState.Idle -> Unit
            DuesUiState.Loading -> SkeletonList(modifier = Modifier.padding(top = 8.dp).testTag(TAG_DUES_LOADING))
            DuesUiState.Empty ->
                EmptyState(
                    title = stringResource(R.string.dues_empty_title),
                    body = stringResource(R.string.dues_nobody_owes),
                    modifier = Modifier.padding(top = 8.dp).testTag(TAG_DUES_EMPTY),
                )
            is DuesUiState.Loaded -> Loaded(state, actions)
            is DuesUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    modifier = Modifier.padding(top = 8.dp).testTag(TAG_DUES_ERROR),
                    // Offered only where the SERVER said retrying could
                    // work [TC-9].
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
        }
    }
}

/**
 * The loaded list: headline, filters, then the groups in the server's
 * order.
 *
 * @param state The loaded state
 * @param actions What the buttons do
 */
@Composable
private fun Loaded(state: DuesUiState.Loaded, actions: DuesActions) {
    RemindOutcome(state.remind, state.summary.remindable, actions)
    LazyColumn(
        modifier = Modifier.testTag(TAG_DUES_LIST),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item { SummaryCard(state.summary) }
        item { Filters(state, actions) }
        if (state.rows.isEmpty()) {
            item {
                Text(
                    stringResource(R.string.dues_filter_empty),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 16.dp),
                )
            }
        }
        state.summary.groups.forEach { group ->
            val rows = state.rows.filter { it.group == group.kind }
            if (rows.isNotEmpty()) groupSection(group, rows)
        }
        item { Box(Modifier.height(16.dp)) }
    }
}

/**
 * One group: its heading and total, then its rows in one card.
 *
 * @param group The group's total
 * @param rows Its rows, in the server's order
 */
private fun LazyListScope.groupSection(group: DuesGroupTotal, rows: List<DuesRow>) {
    item(key = "group-${group.kind}") {
        Row(
            Modifier.fillMaxWidth().padding(top = 6.dp).testTag(TAG_DUES_GROUP),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                stringResource(groupLabel(group.kind)),
                style = GroupHeading,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(Numerals.money(group.total), style = GroupHeading, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    item(key = "rows-${group.kind}") {
        Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)) {
            rows.forEachIndexed { index, row ->
                if (index > 0) {
                    HorizontalDivider(
                        Modifier.padding(start = 16.dp),
                        color = MaterialTheme.colorScheme.surfaceContainerHigh,
                    )
                }
                DuesRowItem(row)
            }
        }
    }
}

/**
 * "Owed to you", the bar of the three groups, and its legend.
 *
 * @param summary The server's totals
 */
@Composable
private fun SummaryCard(summary: DuesSummary) {
    ShikkhokCard(Modifier.testTag(TAG_DUES_SUMMARY)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
            Column(Modifier.weight(1f)) {
                Text(
                    stringResource(R.string.dues_owed_to_you),
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(Numerals.money(summary.total), style = MaterialTheme.typography.headlineLarge)
            }
            Text(
                stringResource(R.string.dues_students, Numerals.count(summary.count)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(bottom = 8.dp),
            )
        }
        ShareBar(summary.groups)
        summary.groups.forEach { group -> Legend(group) }
    }
}

/**
 * The stacked bar, each part as wide as the share the server sent.
 *
 * @param groups The groups
 */
@Composable
private fun ShareBar(groups: List<DuesGroupTotal>) {
    fun totalOf(kind: DuesGroupKind): String =
        groups.firstOrNull { it.kind == kind }?.total?.let(Numerals::money).orEmpty()
    val description =
        stringResource(
            R.string.dues_bar_description,
            totalOf(DuesGroupKind.OVER_30),
            totalOf(DuesGroupKind.LATE),
            totalOf(DuesGroupKind.NOT_LATE),
        )
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp)
            .height(12.dp)
            .semantics { contentDescription = description },
    ) {
        groups.filter { it.share > 0 }.forEach { group ->
            Swatch(group.kind, Modifier.weight(group.share.toFloat()).height(12.dp))
        }
    }
}

/**
 * One legend line: swatch, label and count, total.
 *
 * @param group The group
 */
@Composable
private fun Legend(group: DuesGroupTotal) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 24.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Swatch(group.kind, Modifier.size(12.dp))
        Text(
            stringResource(R.string.dues_legend, stringResource(groupLabel(group.kind)), Numerals.count(group.count)),
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f),
        )
        Text(
            Numerals.money(group.total),
            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
        )
    }
}

/**
 * A group's colour: solid red, pale red, or an outlined blank.
 *
 * @param kind The group
 * @param modifier Its size
 */
@Composable
private fun Swatch(kind: DuesGroupKind, modifier: Modifier) {
    val shape = RoundedCornerShape(3.dp)
    when (kind) {
        DuesGroupKind.OVER_30 -> Box(modifier.background(MaterialTheme.colorScheme.error, shape))
        DuesGroupKind.LATE -> Box(modifier.background(LateSwatch, shape))
        DuesGroupKind.NOT_LATE ->
            Box(
                modifier
                    .background(MaterialTheme.colorScheme.surface, shape)
                    .border(1.5.dp, MaterialTheme.colorScheme.outline, shape),
            )
    }
}

/**
 * The batch picker and the two filter chips.
 *
 * @param state The loaded state
 * @param actions What the chips do
 */
@Composable
private fun Filters(state: DuesUiState.Loaded, actions: DuesActions) {
    var picking by remember { mutableStateOf(false) }
    // Scrolls sideways rather than squeezing: three chips and a long
    // batch name do not fit a 360dp phone in Bangla.
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box {
            FilterPill(
                text = (state.batch?.name ?: stringResource(R.string.dues_filter_all_batches)) + "  ▾",
                on = state.batch != null,
                onClick = { picking = true },
            )
            DropdownMenu(expanded = picking, onDismissRequest = { picking = false }) {
                DropdownMenuItem(
                    text = { Text(stringResource(R.string.dues_filter_all_batches)) },
                    onClick = {
                        picking = false
                        actions.onNarrow(null)
                    },
                )
                state.batches.forEach { batch ->
                    DropdownMenuItem(
                        text = { Text(Numerals.freeText(batch.name)) },
                        onClick = {
                            picking = false
                            actions.onNarrow(batch)
                        },
                    )
                }
            }
        }
        FilterPill(
            text = stringResource(R.string.dues_filter_late),
            on = state.filter == DuesFilter.LATE_ONLY,
            onClick = { actions.onFilter(toggled(state.filter, DuesFilter.LATE_ONLY)) },
        )
        FilterPill(
            text = stringResource(R.string.dues_filter_not_reminded),
            on = state.filter == DuesFilter.NOT_REMINDED,
            onClick = { actions.onFilter(toggled(state.filter, DuesFilter.NOT_REMINDED)) },
        )
    }
}

/**
 * Tapping the open filter closes it.
 *
 * @param current The open filter
 * @param tapped The chip tapped
 * @return The filter to open
 */
private fun toggled(current: DuesFilter, tapped: DuesFilter): DuesFilter =
    if (current == tapped) DuesFilter.ALL else tapped

/**
 * A 32dp filter chip: tonal with a tick when on, outlined when off.
 *
 * @param text Its label
 * @param on Whether it is on
 * @param onClick Called when tapped
 */
@Composable
private fun FilterPill(text: String, on: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(8.dp)
    Surface(
        shape = shape,
        color = if (on) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface,
        contentColor =
            if (on) MaterialTheme.colorScheme.onSecondaryContainer else MaterialTheme.colorScheme.onSurfaceVariant,
        modifier =
            Modifier
                .heightIn(min = 32.dp)
                .then(if (on) Modifier else Modifier.border(1.dp, MaterialTheme.colorScheme.outline, shape))
                .clickable(onClick = onClick)
                .testTag(TAG_DUES_FILTER),
    ) {
        Text(
            (if (on) "✓ " else "") + text,
            style = MaterialTheme.typography.labelLarge,
            maxLines = 1,
            softWrap = false,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
        )
    }
}

/**
 * One row: who, which batch and months, the reminder line; the amount
 * and how late.
 *
 * @param row The row to render
 */
@Composable
private fun DuesRowItem(row: DuesRow) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 72.dp)
            .padding(horizontal = 16.dp, vertical = 10.dp)
            .testTag(TAG_DUES_ROW),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(Numerals.freeText(row.displayName), style = MaterialTheme.typography.bodyLarge)
            Text(
                listOfNotNull(Numerals.freeText(row.batchName), monthRange(row)).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            ReminderLine(row)
        }
        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                Numerals.money(row.outstanding),
                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold),
                modifier = Modifier.testTag(TAG_DUES_AMOUNT),
            )
            row.daysLate?.let { days ->
                PaymentStateChip(
                    if (row.group == DuesGroupKind.OVER_30) PaymentState.OVERDUE else PaymentState.PARTIAL,
                    stringResource(R.string.dues_days, Numerals.count(days)),
                    modifier = Modifier.testTag(TAG_DUES_DAYS),
                    compact = true,
                )
            }
        }
    }
}

/**
 * "Reminded 3 d ago", or a loud "Never reminded" for the longest-late
 * group, as the board draws them.
 *
 * @param row The row
 */
@Composable
private fun ReminderLine(row: DuesRow) {
    val reminded = row.lastRemindedAt
    when {
        reminded != null ->
            Text(
                stringResource(R.string.dues_reminded, ago(reminded)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        row.group == DuesGroupKind.OVER_30 ->
            Text(
                stringResource(R.string.dues_never_reminded),
                style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.error,
            )
    }
}

/**
 * The months a debt spans, as `Aug–Oct`, or one month alone.
 *
 * @param row The row
 * @return The range, or null when the server named no period
 */
@Composable
private fun monthRange(row: DuesRow): String? {
    val first = row.oldestUnpaidPeriod ?: return null
    val last = row.latestUnpaidPeriod
    return if (last == null || last == first) monthName(first) else "${monthName(first)}–${monthName(last)}"
}

/**
 * The bar above the navigation: "Remind N late students".
 *
 * @param count How many seats the server says a reminder would reach
 * @param sending Whether one is on its way
 * @param onClick Called when tapped
 */
@Composable
private fun RemindBar(count: Int, sending: Boolean, onClick: () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 16.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
        PrimaryButton(
            text = stringResource(R.string.dues_remind_button, Numerals.count(count)),
            onClick = onClick,
            enabled = !sending,
            modifier = Modifier.fillMaxWidth().testTag(TAG_DUES_REMIND),
            leading = {
                Icon(painterResource(R.drawable.ic_bell), contentDescription = null, Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
            },
        )
        Text(
            stringResource(R.string.dues_remind_note),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/**
 * The confirmation, and what a reminder did.
 *
 * @param remind Where it stands
 * @param count How many seats it would reach
 * @param actions What the buttons do
 */
@Composable
private fun RemindOutcome(remind: RemindState, count: Int, actions: DuesActions) {
    when (remind) {
        RemindState.Confirming -> RemindConfirm(count, actions)
        is RemindState.Sent ->
            Banner(
                title = stringResource(R.string.dues_remind_sent, Numerals.count(remind.sent)),
                modifier = Modifier.padding(top = 8.dp).testTag(TAG_DUES_REMIND_RESULT),
                action = { TextAction(stringResource(R.string.action_ok), actions.onDismissRemind) },
            )
        is RemindState.Failed ->
            Banner(
                title = stringResource(MessageKeys.resolve(remind.messageKey)),
                tone = BannerTone.ERROR,
                modifier = Modifier.padding(top = 8.dp).testTag(TAG_DUES_REMIND_RESULT),
                action = { TextAction(stringResource(R.string.action_ok), actions.onDismissRemind) },
            )
        RemindState.Idle, RemindState.Sending -> Unit
    }
}

/**
 * "Remind N students?", with what they will see.
 *
 * @param count How many seats it would reach
 * @param actions What the buttons do
 */
@Composable
private fun RemindConfirm(count: Int, actions: DuesActions) {
    AlertDialog(
        onDismissRequest = actions.onDismissRemind,
        title = { Text(stringResource(R.string.dues_remind_confirm_title, Numerals.count(count))) },
        text = { Text(stringResource(R.string.dues_remind_confirm_body)) },
        confirmButton = {
            TextButton(onClick = actions.onRemind, modifier = Modifier.testTag(TAG_DUES_REMIND_SEND)) {
                Text(stringResource(R.string.dues_remind_send))
            }
        },
        dismissButton = {
            TextButton(onClick = actions.onDismissRemind) { Text(stringResource(R.string.dues_remind_cancel)) }
        },
    )
}

/**
 * A group's name.
 *
 * @param kind The group
 * @return Its string resource
 */
private fun groupLabel(kind: DuesGroupKind): Int =
    when (kind) {
        DuesGroupKind.OVER_30 -> R.string.dues_group_over_30
        DuesGroupKind.LATE -> R.string.dues_group_late
        DuesGroupKind.NOT_LATE -> R.string.dues_group_not_late
    }

/** The board's group headings: 14/22 bold. */
private val GroupHeading
    @Composable get() = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold)

/** The 1-30 days late swatch, #E8908A on the board. */
private val LateSwatch = Color(0xFFE8908A)
