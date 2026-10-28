package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.network.ScheduleSlotDto

/** One weekday chip. */
const val TAG_SCHEDULE_DAY: String = "schedule_day"

/** The start-time button. */
const val TAG_SCHEDULE_START: String = "schedule_start"

/** The end-time button. */
const val TAG_SCHEDULE_END: String = "schedule_end"

/** Shown when the end is not after the start. */
const val TAG_SCHEDULE_ORDER_ERROR: String = "schedule_order_error"

/**
 * The weekdays in the order a Bangladeshi week runs, Saturday first,
 * as the server numbers them (0 = Monday ... 6 = Sunday).
 */
val WEEK_ORDER: List<Int> = listOf(5, 6, 0, 1, 2, 3, 4)

/** Noon, the boundary between am and pm. */
private const val NOON = 12

/** `HH:MM` out of a time the server may send as `HH:MM:SS`. */
private const val HHMM_LENGTH = 5

/**
 * A schedule being edited: some days, one time range for all of them.
 *
 * **One range for every day**, because that is how the canvas draws a
 * batch's schedule ("Sat · Mon · Wed", "4:00-5:30 pm") and how T0 asks
 * for it ("pick its class days, time"). A stored schedule whose days
 * have different times is read from its first slot; the app only ever
 * writes uniform ones.
 *
 * @property days The chosen weekdays, server-numbered
 * @property start The start, `HH:MM`
 * @property end The end, `HH:MM`
 */
data class ScheduleDraft(
    val days: Set<Int> = emptySet(),
    val start: String = "16:00",
    val end: String = "17:00",
) {
    /** True unless days are chosen and the class ends at or before it starts. */
    val isValid: Boolean
        get() = days.isEmpty() || end > start

    /**
     * The slots to send, in week order.
     *
     * @return One slot per chosen day
     */
    fun toSlots(): List<ScheduleSlotDto> =
        WEEK_ORDER.filter { it in days }.map { ScheduleSlotDto(it, start, end) }

    companion object {
        /**
         * Read a stored schedule back into a draft.
         *
         * @param slots The stored slots
         * @return The draft, or the default when there are none
         */
        fun of(slots: List<ScheduleSlotDto>): ScheduleDraft =
            slots.firstOrNull()?.let { first ->
                ScheduleDraft(slots.map { it.weekday }.toSet(), first.startTime, first.endTime)
            } ?: ScheduleDraft()
    }
}

/**
 * A clock time for people, in the 12-hour form the canvas uses.
 *
 * Latin digits whatever the language, per the numeral rule.
 *
 * @param hhmm A time as `HH:MM`
 * @return e.g. `4:00 pm`
 */
fun displayTime(hhmm: String): String {
    val (hour, minute) = hhmm.split(":").map(String::toInt)
    val twelve = if (hour % NOON == 0) NOON else hour % NOON
    val half = if (hour < NOON) "am" else "pm"
    return "%d:%02d %s".format(java.util.Locale.ENGLISH, twelve, minute, half)
}

/**
 * A schedule in one line, as the cards show it: `Sat · Mon · 4:00 pm`.
 *
 * Days in Bangladeshi week order and the first slot's start, since the
 * app writes one time for every day; empty when there are no slots.
 *
 * @param slots The weekly classes
 * @return The line
 */
@Composable
fun scheduleSummary(slots: List<ScheduleSlotDto>): String {
    val first = slots.firstOrNull() ?: return ""
    val days = WEEK_ORDER.filter { day -> slots.any { it.weekday == day } }
    val names = days.map { stringResource(dayName(it)) }
    return (names + displayTime(first.startTime.take(HHMM_LENGTH))).joinToString(" · ")
}

/**
 * Pick a batch's class days and their time.
 *
 * @param draft The schedule being edited
 * @param onChange Called with every edit
 * @param modifier The layout modifier
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ScheduleEditor(
    draft: ScheduleDraft,
    onChange: (ScheduleDraft) -> Unit,
    modifier: Modifier = Modifier,
) {
    var picking by remember { mutableStateOf<String?>(null) }

    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.schedule_days), style = MaterialTheme.typography.labelLarge)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            WEEK_ORDER.forEach { day ->
                FilterChip(
                    selected = day in draft.days,
                    onClick = {
                        onChange(
                            draft.copy(
                                days = if (day in draft.days) draft.days - day else draft.days + day,
                            ),
                        )
                    },
                    label = { Text(stringResource(dayName(day))) },
                    modifier = Modifier.testTag(TAG_SCHEDULE_DAY),
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = { picking = "start" },
                modifier = Modifier.weight(1f).testTag(TAG_SCHEDULE_START),
            ) { Text(stringResource(R.string.schedule_start, displayTime(draft.start))) }
            OutlinedButton(
                onClick = { picking = "end" },
                modifier = Modifier.weight(1f).testTag(TAG_SCHEDULE_END),
            ) { Text(stringResource(R.string.schedule_end, displayTime(draft.end))) }
        }
        if (!draft.isValid) {
            Text(
                stringResource(R.string.schedule_end_before_start),
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.testTag(TAG_SCHEDULE_ORDER_ERROR),
            )
        }
    }

    picking?.let { which ->
        TimeDialog(
            initial = if (which == "start") draft.start else draft.end,
            onPicked = { picked ->
                onChange(if (which == "start") draft.copy(start = picked) else draft.copy(end = picked))
                picking = null
            },
            onDismiss = { picking = null },
        )
    }
}

/**
 * A time picker in a dialog, answering `HH:MM`.
 *
 * @param initial The time it opens on, `HH:MM`
 * @param onPicked Called with the chosen time
 * @param onDismiss Called when backed out of
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TimeDialog(initial: String, onPicked: (String) -> Unit, onDismiss: () -> Unit) {
    val (hour, minute) = initial.split(":").map(String::toInt)
    val state = rememberTimePickerState(initialHour = hour, initialMinute = minute, is24Hour = false)
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(
                onClick = {
                    // The picker reports the hour 0-23 even in 12-hour
                    // mode, so this is already the wire form.
                    onPicked("%02d:%02d".format(java.util.Locale.ENGLISH, state.hour, state.minute))
                },
            ) { Text(stringResource(R.string.action_ok)) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.action_cancel)) }
        },
        text = { TimePicker(state = state) },
    )
}

/**
 * Name one weekday.
 *
 * @param day Server-numbered, 0 = Monday
 * @return Its short-name string resource
 */
private fun dayName(day: Int): Int =
    when (day) {
        0 -> R.string.weekday_mon
        1 -> R.string.weekday_tue
        2 -> R.string.weekday_wed
        3 -> R.string.weekday_thu
        4 -> R.string.weekday_fri
        5 -> R.string.weekday_sat
        else -> R.string.weekday_sun
    }
