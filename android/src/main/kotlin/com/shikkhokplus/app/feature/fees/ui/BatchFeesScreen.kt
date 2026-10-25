package com.shikkhokplus.app.feature.fees.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.fees.RosterFeeRow

/** Stable test identifiers. Not user-visible text. */
const val TAG_BATCH_FEES_LIST: String = "batch_fees_list"

/** One seat's fee position. */
const val TAG_BATCH_FEES_ROW: String = "batch_fees_row"

/** The explanation shown when no seat owes anything. */
const val TAG_BATCH_FEES_EMPTY: String = "batch_fees_empty"

/** The per-row reminder action. */
const val TAG_BATCH_FEES_REMIND: String = "batch_fees_remind"

/** The per-row reminded state, derived from the latest event. */
const val TAG_BATCH_FEES_REMINDED: String = "batch_fees_reminded"

/**
 * What each student owes, as their teacher sees it.
 *
 * **No composable here compares a domain value.** The row carries
 * `owesSomething` and `statusLabel` as fields the mapper decided, so
 * `if (row.outstanding > Money.ZERO)` never appears in this file —
 * which is the specific erosion the team practice names for the fee
 * surface.
 *
 * **The collection number is deliberately absent** [BR6.4, NFR14.33].
 * It reaches exactly one response in the product and a listing is not
 * it; a gate over the generated schema asserts that as an equality, so
 * adding it here would fail the build rather than merely be wrong.
 *
 * @param rows The seats, as the mapper produced them
 * @param remindedLabels A reminder's derived state per enrollment, or
 *   absent where none was ever sent. **Derived server-side from the
 *   latest event** [BR7.1]; the client renders the label and computes
 *   no "days ago" of its own
 * @param onRemind Send a reminder for one seat
 * @param modifier Layout modifier
 */
@Composable
fun BatchFeesScreen(
    rows: List<RosterFeeRow>,
    remindedLabels: Map<String, String> = emptyMap(),
    onRemind: (RosterFeeRow) -> Unit = {},
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (rows.isEmpty()) {
            Text(
                stringResource(R.string.batch_fees_empty),
                Modifier.testTag(TAG_BATCH_FEES_EMPTY),
            )
            return@Column
        }

        LazyColumn(
            modifier = Modifier.testTag(TAG_BATCH_FEES_LIST),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(rows, key = { it.enrollmentId }) { row ->
                SeatFeeRow(
                    row = row,
                    remindedLabel = remindedLabels[row.enrollmentId],
                    onRemind = onRemind,
                )
            }
        }
    }
}

/**
 * One seat's fee position.
 *
 * @param row The seat to render
 * @param remindedLabel The derived reminded state, or null for never
 * @param onRemind Send a reminder for this seat
 */
@Composable
private fun SeatFeeRow(
    row: RosterFeeRow,
    remindedLabel: String?,
    onRemind: (RosterFeeRow) -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth().testTag(TAG_BATCH_FEES_ROW),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(row.displayName, style = MaterialTheme.typography.titleSmall)
        Text(
            stringResource(
                R.string.fees_outstanding_total,
                Numerals.money(row.outstanding),
            ),
            // `owesSomething` is a MAPPER field. The alternative --
            // comparing the amount here -- is the same rule written
            // where it looks like presentation.
            color =
                if (row.owesSomething) {
                    MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
        )
        if (row.statusLabel != null) {
            Text(stringResource(MessageKeys.resolve(row.statusLabel)))
        }
        if (row.dueDateLabel != null) {
            Text(
                stringResource(R.string.fees_due_on, row.dueDateLabel),
                style = MaterialTheme.typography.bodySmall,
            )
        }
        Text(
            remindedLabel ?: stringResource(R.string.fees_never_reminded),
            modifier = Modifier.testTag(TAG_BATCH_FEES_REMINDED),
            style = MaterialTheme.typography.bodySmall,
        )
        if (row.owesSomething) {
            TextButton(
                onClick = { onRemind(row) },
                modifier = Modifier.testTag(TAG_BATCH_FEES_REMIND),
            ) {
                Text(stringResource(R.string.fees_remind))
            }
        }
    }
}
