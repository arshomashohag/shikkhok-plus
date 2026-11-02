package com.shikkhokplus.app.feature.collections.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.collections.BatchChip
import com.shikkhokplus.app.feature.collections.BatchMonthRow
import com.shikkhokplus.app.feature.collections.BatchRowFailed
import com.shikkhokplus.app.feature.collections.CollectionsUiState
import com.shikkhokplus.app.feature.collections.MonthBar

/** Stable test identifiers. Not user-visible text. */
const val TAG_COLLECTIONS_LOADING: String = "collections_loading"

/** The error card. */
const val TAG_COLLECTIONS_ERROR: String = "collections_error"

/** One batch filter chip. */
const val TAG_COLLECTIONS_CHIP: String = "collections_chip"

/** The "All batches" chip. */
const val TAG_COLLECTIONS_CHIP_ALL: String = "collections_chip_all"

/** One month's pair of bars. */
const val TAG_COLLECTIONS_MONTH: String = "collections_month"

/** One batch's row for the headline month. */
const val TAG_COLLECTIONS_BATCH_ROW: String = "collections_batch_row"

/** A batch row that could not load. */
const val TAG_COLLECTIONS_BATCH_ROW_FAILED: String = "collections_batch_row_failed"

/** The retry control on a failed batch row. */
const val TAG_COLLECTIONS_BATCH_ROW_RETRY: String = "collections_batch_row_retry"

/** The collected tile. */
const val TAG_COLLECTIONS_COLLECTED: String = "collections_collected"

/** The still-owed tile. */
const val TAG_COLLECTIONS_OWED: String = "collections_owed"

/** The full height of a bar at 100 percent. */
val CHART_HEIGHT: Dp = 120.dp

/**
 * What a bar's server percent draws as.
 *
 * @param percent The server's whole percent, 0 to 100
 * @return The bar's height
 */
fun barHeight(percent: Int): Dp = CHART_HEIGHT * (percent.coerceIn(0, MAX_PERCENT) / MAX_PERCENT.toFloat())

private const val MAX_PERCENT = 100

/**
 * What the callbacks of the collections screen do.
 *
 * @property onRetry Ask again after a failure
 * @property onToggleBatch A batch chip was tapped
 * @property onShowAll The "All batches" chip was tapped
 * @property onSelectMonth A month's bars were tapped
 * @property onRetryBatch Retry one batch row that failed to load
 * @property onOpenBatch A batch row was tapped, with the month it shows
 * @property onBack The back arrow
 */
data class CollectionsActions(
    val onRetry: () -> Unit = {},
    val onToggleBatch: (String) -> Unit = {},
    val onShowAll: () -> Unit = {},
    val onSelectMonth: (String) -> Unit = {},
    val onRetryBatch: (String) -> Unit = {},
    val onOpenBatch: (BatchMonthRow) -> Unit = {},
    val onBack: (() -> Unit)? = null,
)

/**
 * M1: collected versus charged, by month, across the teacher's batches.
 *
 * Every figure and every bar height is the server's; the phone draws a
 * bar by multiplying a whole percent by a height and never reads a
 * money string as a number [TC-9, D-20].
 *
 * @param state What to render
 * @param actions What the controls do
 * @param modifier Layout modifier
 * @param bottomBar The navigation bar, if any
 */
@Composable
fun CollectionsScreen(
    state: CollectionsUiState,
    actions: CollectionsActions,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
) {
    ListScreenScaffold(
        title = stringResource(R.string.collections_title),
        modifier = modifier,
        onBack = actions.onBack,
        bottomBar = bottomBar,
    ) {
        when (state) {
            CollectionsUiState.Loading ->
                SkeletonList(modifier = Modifier.padding(top = 8.dp).testTag(TAG_COLLECTIONS_LOADING))
            is CollectionsUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    modifier = Modifier.padding(top = 8.dp).testTag(TAG_COLLECTIONS_ERROR),
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            is CollectionsUiState.Loaded -> Report(state, actions)
        }
    }
}

@Composable
private fun Report(
    state: CollectionsUiState.Loaded,
    actions: CollectionsActions,
) {
    Column(
        modifier = Modifier.padding(top = 8.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        BatchChips(state.batches, actions)
        if (state.months.isEmpty()) {
            Text(stringResource(R.string.collections_empty))
            return
        }
        Tiles(state)
        Chart(state.months, state.headlinePeriod, actions.onSelectMonth)
        state.headlinePeriod?.let { period ->
            Text(
                stringResource(R.string.collections_by_batch, monthName(period, short = false)),
                style = MaterialTheme.typography.titleSmall,
            )
            state.batchRows.forEach { row ->
                when (row) {
                    is BatchMonthRow -> BatchRowCard(row, actions.onOpenBatch)
                    is BatchRowFailed -> FailedBatchRow(row, actions.onRetryBatch)
                }
            }
        }
    }
}

@Composable
private fun BatchChips(
    batches: List<BatchChip>,
    actions: CollectionsActions,
) {
    LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            FilterPill(
                text = stringResource(R.string.dues_filter_all_batches),
                on = batches.none { it.selected },
                onClick = actions.onShowAll,
                tag = TAG_COLLECTIONS_CHIP_ALL,
            )
        }
        items(batches, key = { it.id }) { chip ->
            FilterPill(chip.name, chip.selected, { actions.onToggleBatch(chip.id) }, TAG_COLLECTIONS_CHIP)
        }
    }
}

@Composable
private fun Tiles(state: CollectionsUiState.Loaded) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        ShikkhokCard(Modifier.weight(1f).testTag(TAG_COLLECTIONS_COLLECTED)) {
            state.headlinePeriod?.let {
                Text(
                    stringResource(R.string.collections_collected_in, monthName(it)),
                    style = MaterialTheme.typography.labelMedium,
                )
            }
            state.headlineCollected?.let {
                Text(Numerals.money(it), style = MaterialTheme.typography.headlineSmall)
            }
            state.headlineCharged?.let {
                Text(
                    stringResource(R.string.collections_of_charged, Numerals.money(it)),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
        ShikkhokCard(Modifier.weight(1f).testTag(TAG_COLLECTIONS_OWED)) {
            Text(
                stringResource(R.string.collections_still_owed),
                style = MaterialTheme.typography.labelMedium,
            )
            Text(Numerals.money(state.outstanding), style = MaterialTheme.typography.headlineSmall)
            Text(
                stringResource(R.string.collections_students_owing, state.owingStudents),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun Chart(
    months: List<MonthBar>,
    selected: String?,
    onSelect: (String) -> Unit,
) {
    val inProgress = months.firstOrNull { it.inProgress }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.collections_last_months), style = MaterialTheme.typography.titleSmall)
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Bottom,
        ) {
            months.forEach { bar -> MonthColumn(bar, bar.period == selected, onSelect) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Legend(MaterialTheme.colorScheme.primary, stringResource(R.string.collections_legend_collected))
            Legend(MaterialTheme.colorScheme.outlineVariant, stringResource(R.string.collections_legend_charged))
        }
        inProgress?.let {
            Text(
                "* " + stringResource(R.string.collections_in_progress_note, monthName(it.period, short = false)),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun MonthColumn(
    bar: MonthBar,
    selected: Boolean,
    onSelect: (String) -> Unit,
) {
    val name = monthName(bar.period)
    val description =
        if (bar.inProgress) stringResource(R.string.collections_in_progress_desc, name) else name
    Column(
        modifier =
            Modifier
                .heightIn(min = 48.dp)
                .clickable { onSelect(bar.period) }
                .semantics { contentDescription = description }
                .testTag(TAG_COLLECTIONS_MONTH),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(2.dp), verticalAlignment = Alignment.Bottom) {
            Box(
                Modifier
                    .width(12.dp)
                    .height(barHeight(bar.collectedBar))
                    .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(topStart = 3.dp, topEnd = 3.dp)),
            )
            Box(
                Modifier
                    .width(12.dp)
                    .height(barHeight(bar.chargedBar))
                    .background(
                        MaterialTheme.colorScheme.outlineVariant,
                        RoundedCornerShape(topStart = 3.dp, topEnd = 3.dp),
                    ),
            )
        }
        Text(
            name + if (bar.inProgress) "*" else "",
            style = MaterialTheme.typography.labelSmall,
            color =
                if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun Legend(
    colour: androidx.compose.ui.graphics.Color,
    text: String,
) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(Modifier.width(12.dp).height(12.dp).background(colour, RoundedCornerShape(2.dp)))
        Text(text, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun BatchRowCard(
    row: BatchMonthRow,
    onOpen: (BatchMonthRow) -> Unit,
) {
    ShikkhokCard(Modifier.testTag(TAG_COLLECTIONS_BATCH_ROW), onClick = { onOpen(row) }) {
        Text(row.name, style = MaterialTheme.typography.titleSmall)
        Text(
            stringResource(
                R.string.collections_batch_amounts,
                Numerals.money(row.collected),
                Numerals.money(row.charged),
            ),
        )
        Text(
            stringResource(
                R.string.collections_batch_counts,
                row.counts.paid,
                row.counts.checking,
                row.counts.owed,
            ),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun FailedBatchRow(
    row: BatchRowFailed,
    onRetry: (String) -> Unit,
) {
    ShikkhokCard(Modifier.testTag(TAG_COLLECTIONS_BATCH_ROW_FAILED)) {
        Text(row.name, style = MaterialTheme.typography.titleSmall)
        Text(
            stringResource(MessageKeys.resolve(row.messageKey)),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (row.retryable) {
            TextAction(
                text = stringResource(R.string.dues_retry),
                onClick = { onRetry(row.batchId) },
                modifier = Modifier.testTag(TAG_COLLECTIONS_BATCH_ROW_RETRY),
            )
        }
    }
}

/**
 * A 32dp filter chip: tonal with a tick when on, outlined when off.
 *
 * @param text Its label
 * @param on Whether it is on
 * @param onClick Called when tapped
 * @param tag Its test identifier
 */
@Composable
fun FilterPill(
    text: String,
    on: Boolean,
    onClick: () -> Unit,
    tag: String,
) {
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
                .testTag(tag),
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
