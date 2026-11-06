package com.shikkhokplus.app.feature.expenses.ui

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.monthName
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.expenses.CategoryTotal
import com.shikkhokplus.app.feature.expenses.ExpenseCategory

/** The previous-month control. */
const val TAG_MONTH_PREVIOUS: String = "money_month_previous"

/** The next-month control. */
const val TAG_MONTH_NEXT: String = "money_month_next"

/**
 * The string naming a category, in the person's language.
 *
 * @param category The category
 * @return Its string resource
 */
@StringRes
fun categoryLabel(category: ExpenseCategory): Int =
    when (category) {
        ExpenseCategory.EXAM_PAPER -> R.string.expenses_cat_exam_paper
        ExpenseCategory.PRINTING -> R.string.expenses_cat_printing
        ExpenseCategory.RENT -> R.string.expenses_cat_rent
        ExpenseCategory.UTILITIES -> R.string.expenses_cat_utilities
        ExpenseCategory.MATERIALS -> R.string.expenses_cat_materials
        ExpenseCategory.TRANSPORT -> R.string.expenses_cat_transport
        ExpenseCategory.SALARY -> R.string.expenses_cat_salary
        ExpenseCategory.OTHER -> R.string.expenses_cat_other
    }

/**
 * The month being shown, with a step either side; no step past this month.
 *
 * @param month `YYYY-MM`
 * @param canGoForward Whether a later month exists to show
 * @param onShift Called with -1 or 1
 */
@Composable
fun MonthBar(
    month: String,
    canGoForward: Boolean,
    onShift: (Long) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        val previous = stringResource(R.string.calendar_prev_month)
        val next = stringResource(R.string.calendar_next_month)
        TextAction(
            text = "‹",
            onClick = { onShift(-1) },
            modifier = Modifier.testTag(TAG_MONTH_PREVIOUS).semantics { contentDescription = previous },
        )
        Text(
            text = monthName(month, short = false),
            style = MaterialTheme.typography.titleMedium,
            textAlign = TextAlign.Center,
            modifier = Modifier.weight(1f).asHeading(),
        )
        TextAction(
            text = "›",
            onClick = { onShift(1) },
            enabled = canGoForward,
            modifier = Modifier.testTag(TAG_MONTH_NEXT).semantics { contentDescription = next },
        )
    }
}

/**
 * A titled card of label-and-amount lines.
 *
 * @param title The section's heading, or null
 * @param lines Each line's label and amount
 * @param total A last, emphasised line, or null
 */
@Composable
fun MoneyLines(
    title: String?,
    lines: List<Pair<String, Money>>,
    total: Pair<String, Money>? = null,
) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        title?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.asHeading(),
            )
        }
        ShikkhokCard {
            lines.forEach { (label, amount) -> MoneyLine(label, amount, emphasised = false) }
            total?.let { (label, amount) -> MoneyLine(label, amount, emphasised = true) }
        }
    }
}

/**
 * The server's total per category, as money lines.
 *
 * @param title The section's heading
 * @param totals The totals
 */
@Composable
fun CategoryLines(title: String, totals: List<CategoryTotal>) {
    MoneyLines(
        title = title,
        lines = totals.map { stringResource(categoryLabel(it.category)) to it.total },
    )
}

@Composable
private fun MoneyLine(label: String, amount: Money, emphasised: Boolean) {
    val weight = if (emphasised) FontWeight.SemiBold else FontWeight.Normal
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = weight,
            modifier = Modifier.weight(1f),
        )
        Text(text = Numerals.money(amount), style = MaterialTheme.typography.bodyLarge, fontWeight = weight)
    }
}
