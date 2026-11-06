package com.shikkhokplus.app.feature.batchdetail.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.ui.scheduleDays
import com.shikkhokplus.app.core.ui.scheduleRange
import com.shikkhokplus.app.feature.batchdetail.BatchHeader
import com.shikkhokplus.app.feature.batchdetail.BatchTab
import java.util.Locale

/** One tab. */
const val TAG_BATCH_TAB: String = "batch_tab"

/** The add button, whose words follow the tab. */
const val TAG_BATCH_FAB: String = "batch_fab"

/** The link to the batch's schedule. */
const val TAG_BATCH_SCHEDULE: String = "batch_schedule"

/** The exam and other fees chip in the batch header. */
const val TAG_BATCH_EXTRA_FEES: String = "batch_extra_fees"

/** The pencil that opens the batch's edit form. */
const val TAG_BATCH_EDIT: String = "batch_edit"

/** One information tag under the title. */
const val TAG_BATCH_INFO: String = "batch_info"

/**
 * T7: one batch, with its students, classes, exams and notices as tabs.
 *
 * @param batchName The batch's name, known before the header loads
 * @param header The batch summary, or null until read
 * @param tab The open tab
 * @param onSelect Called with a tab
 * @param onBack Called to leave
 * @param onAdd Called by the add button, for the open tab
 * @param onSchedule Called to edit the batch's class days and time
 * @param onEdit Called to edit the batch's name, subjects and fee
 * @param onExtraFees Called to open the batch's exam and other fees, or
 *   null where the chip is not drawn
 * @param modifier The layout modifier
 * @param showAdd Whether to draw the add button for the open tab
 * @param content The open tab's contents
 */
@Composable
fun BatchDetailScreen(
    batchName: String,
    header: BatchHeader?,
    tab: BatchTab,
    onSelect: (BatchTab) -> Unit,
    onBack: () -> Unit,
    onAdd: () -> Unit,
    onSchedule: () -> Unit,
    onEdit: () -> Unit = {},
    onExtraFees: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
    showAdd: Boolean = tab != BatchTab.NOTICES,
    content: @Composable () -> Unit,
) {
    ListScreenScaffold(
        title = Numerals.freeText(header?.name ?: batchName),
        subtitle = header?.let { feeLine(it) },
        onBack = onBack,
        actions = {
            IconButton(onClick = onEdit, modifier = Modifier.testTag(TAG_BATCH_EDIT)) {
                Icon(
                    painterResource(R.drawable.ic_edit),
                    stringResource(R.string.batch_edit_title),
                    Modifier.size(22.dp),
                )
            }
        },
        modifier = modifier,
        header = {
            header?.let { InfoTags(it, onSchedule, onExtraFees) }
            Tabs(tab, onSelect)
        },
    ) {
        Box(Modifier.fillMaxSize()) {
            content()
            // **No add button where the tab has its own** (T7): Notices
            // writes from its inline composer, and an empty roster's
            // "Add first student" is the one action on screen.
            if (showAdd) ExtendedFloatingActionButton(
                onClick = onAdd,
                shape = MaterialTheme.shapes.large,
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary,
                modifier = Modifier.align(Alignment.BottomEnd).padding(bottom = 16.dp).testTag(TAG_BATCH_FAB),
            ) {
                Text("+  " + stringResource(addLabel(tab)), style = MaterialTheme.typography.titleSmall)
            }
        }
    }
}

/**
 * The bar's subtitle: the monthly fee and when it falls due.
 *
 * @param header The batch summary
 * @return The line, or null when no fee is set
 */
@Composable
private fun feeLine(header: BatchHeader): String? {
    val fee = header.defaultFee ?: return null
    val day = header.feeDueDay ?: return stringResource(R.string.batch_fee_monthly, Numerals.money(fee))
    return stringResource(R.string.batch_fee_due, Numerals.money(fee), ordinal(day))
}

/**
 * A day of the month as the English board writes it (`10th`), and as a
 * plain Latin number in any other language.
 *
 * @param day The day of the month
 * @return Its ordinal
 */
private fun ordinal(day: Int): String {
    if (Locale.getDefault().language != Locale.ENGLISH.language) return Numerals.count(day)
    val suffix =
        when {
            day % HUNDRED in TEEN_START..TEEN_END -> "th"
            day % TEN == 1 -> "st"
            day % TEN == 2 -> "nd"
            day % TEN == THREE -> "rd"
            else -> "th"
        }
    return Numerals.count(day) + suffix
}

/**
 * The grey tags under the title: the schedule, which opens its editor,
 * then the subjects.
 *
 * @param header The batch summary
 * @param onSchedule Called to edit the class days and time
 * @param onExtraFees Called to open the exam and other fees, or null
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun InfoTags(header: BatchHeader, onSchedule: () -> Unit, onExtraFees: (() -> Unit)?) {
    // **One icon in the bar** (T7): the schedule is edited from its own
    // chip, so the bar keeps only Edit. With no class days yet the chip
    // reads "Schedule", so the way in never disappears.
    val schedule =
        listOf(scheduleDays(header.schedule), scheduleRange(header.schedule))
            .filter { it.isNotBlank() }
            .ifEmpty { listOf(stringResource(R.string.batch_schedule)) }
    FlowRow(
        Modifier.fillMaxWidth().padding(bottom = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(
            Modifier
                .clip(MaterialTheme.shapes.small)
                .background(MaterialTheme.colorScheme.surfaceContainer)
                .clickable(onClickLabel = stringResource(R.string.batch_schedule), onClick = onSchedule)
                .heightIn(min = 28.dp)
                .padding(horizontal = 10.dp, vertical = 4.dp)
                .testTag(TAG_BATCH_SCHEDULE),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            schedule.forEach { part ->
                Text(
                    Numerals.freeText(part),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
            Icon(
                painterResource(R.drawable.ic_edit),
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(14.dp),
            )
        }
        onExtraFees?.let { open ->
            Text(
                stringResource(R.string.extra_fees_open),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
                modifier =
                    Modifier
                        .clip(MaterialTheme.shapes.small)
                        .background(MaterialTheme.colorScheme.surfaceContainer)
                        .clickable(onClick = open)
                        .heightIn(min = 28.dp)
                        .padding(horizontal = 10.dp, vertical = 4.dp)
                        .testTag(TAG_BATCH_EXTRA_FEES),
            )
        }
        header.subjects.filter { it.isNotBlank() }.forEach { tag ->
            Text(
                Numerals.freeText(tag),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface,
                modifier =
                    Modifier
                        .background(MaterialTheme.colorScheme.surfaceContainer, MaterialTheme.shapes.small)
                        .heightIn(min = 28.dp)
                        .padding(horizontal = 10.dp, vertical = 4.dp)
                        .testTag(TAG_BATCH_INFO),
            )
        }
    }
}

/**
 * The four tabs, with the open one underlined in the primary colour.
 *
 * @param tab The open tab
 * @param onSelect Called with a tab
 */
@Composable
private fun Tabs(tab: BatchTab, onSelect: (BatchTab) -> Unit) {
    TabRow(
        selectedTabIndex = tab.ordinal,
        containerColor = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.primary,
        indicator = { positions ->
            TabRowDefaults.SecondaryIndicator(
                Modifier.tabIndicatorOffset(positions[tab.ordinal]),
                height = 3.dp,
                color = MaterialTheme.colorScheme.primary,
            )
        },
    ) {
        BatchTab.entries.forEach { each ->
            Tab(
                selected = each == tab,
                onClick = { onSelect(each) },
                selectedContentColor = MaterialTheme.colorScheme.primary,
                unselectedContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.heightIn(min = 48.dp).testTag(TAG_BATCH_TAB),
            ) {
                // One line, with the board's narrow side padding: four
                // tabs share a phone's width, and M3's default padding
                // wrapped "Students" onto two lines.
                Text(
                    stringResource(tabLabel(each)),
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    softWrap = false,
                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 12.dp),
                )
            }
        }
    }
}

/**
 * A tab's name.
 *
 * @param tab The tab
 * @return Its string resource
 */
private fun tabLabel(tab: BatchTab): Int =
    when (tab) {
        BatchTab.STUDENTS -> R.string.batch_tab_students
        BatchTab.CLASSES -> R.string.batch_tab_classes
        BatchTab.EXAMS -> R.string.batch_tab_exams
        BatchTab.NOTICES -> R.string.batch_tab_notices
    }

/**
 * The add button's words for a tab.
 *
 * @param tab The open tab
 * @return Its string resource
 */
private fun addLabel(tab: BatchTab): Int =
    when (tab) {
        BatchTab.STUDENTS -> R.string.batch_add_student
        BatchTab.CLASSES -> R.string.batch_add_class
        BatchTab.EXAMS -> R.string.batch_new_exam
        BatchTab.NOTICES -> R.string.batch_write_notice
    }

/** Ordinal arithmetic for the English day suffix. */
private const val TEN = 10
private const val HUNDRED = 100
private const val THREE = 3
private const val TEEN_START = 11
private const val TEEN_END = 13
