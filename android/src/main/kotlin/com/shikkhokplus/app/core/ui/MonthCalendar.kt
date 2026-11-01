package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.format.monthName

private const val DAYS_IN_WEEK = 7
private const val MONTHS_PER_ROW = 3
private const val MONTHS_IN_YEAR = 12
private const val HALF = 0.5f
private const val DOT_SIZE = 6
private const val MARKER_GAP = 2
private val cellShape = RoundedCornerShape(12.dp)

private val GreenTintLight = Color(0xFFDDF1E3)
private val GreenInkLight = Color(0xFF0F5427)
private val GreenFillLight = Color(0xFF0F5427)
private val GreenTintDark = Color(0xFF1E3A29)
private val GreenInkDark = Color(0xFFB8E6C6)
private val GreenFillDark = Color(0xFF7FD39A)
private val OnGreenFillDark = Color(0xFF08210F)

/**
 * The calendar's tag for a day cell, carrying the state it draws.
 *
 * @param state The day's state
 * @param date `YYYY-MM-DD`
 * @return The test tag
 */
fun calendarDayTag(state: CalendarState, date: String): String = "calendar_day_${state.wire}_$date"

/**
 * The calendar's tag for the ring marking the server's today.
 *
 * @param date `YYYY-MM-DD`
 * @return The test tag
 */
fun calendarTodayTag(date: String): String = "calendar_today_$date"

/**
 * A month as a Sunday-first grid.
 *
 * **Draws the state the server sent.** The composable never compares a
 * date to decide whether a day is today, taken or upcoming; it only
 * maps each [CalendarState] to a look. State is also carried by a
 * glyph or a shape, never colour alone.
 *
 * @param year The month's year
 * @param month The month, 1 to 12
 * @param days Days that have classes; others draw as plain numbers
 * @param firstMonth Earliest month the arrows and picker reach
 * @param lastMonth Latest month the arrows and picker reach
 * @param onPickMonth Called with the month the person moved to
 * @param onDay Called when a day with classes is tapped
 * @param modifier Layout modifier
 * @param today The server's date, `YYYY-MM-DD`, ringed whatever its
 *   classes' state; null rings nothing
 */
@Composable
fun MonthCalendar(
    year: Int,
    month: Int,
    days: List<CalendarDayUi>,
    firstMonth: YearMonth,
    lastMonth: YearMonth,
    onPickMonth: (YearMonth) -> Unit,
    onDay: (CalendarDayUi) -> Unit,
    modifier: Modifier = Modifier,
    today: String? = null,
) {
    val shown = YearMonth(year, month)
    var picking by remember { mutableStateOf(false) }
    Column(modifier = modifier.fillMaxWidth()) {
        CalendarHeader(
            shown = shown,
            canGoBack = shown > firstMonth,
            canGoForward = shown < lastMonth,
            onPrevious = { onPickMonth(shown.plusMonths(-1)) },
            onNext = { onPickMonth(shown.plusMonths(1)) },
            onOpenPicker = { picking = true },
        )
        WeekdayRow()
        CalendarGrid(shown, days.associateBy { it.date }, today, onDay)
    }
    if (picking) {
        MonthPicker(
            shown = shown,
            firstMonth = firstMonth,
            lastMonth = lastMonth,
            onPick = {
                picking = false
                onPickMonth(it)
            },
            onDismiss = { picking = false },
        )
    }
}

/** Month name and year, with the arrows either side. */
@Composable
private fun CalendarHeader(
    shown: YearMonth,
    canGoBack: Boolean,
    canGoForward: Boolean,
    onPrevious: () -> Unit,
    onNext: () -> Unit,
    onOpenPicker: () -> Unit,
) {
    val title = "${monthName(shown.toString(), short = false)} ${shown.year}"
    val previousLabel = stringResource(R.string.calendar_prev_month)
    val nextLabel = stringResource(R.string.calendar_next_month)
    val pickLabel = stringResource(R.string.calendar_pick_month, title)
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        TextButton(
            onClick = onPrevious,
            enabled = canGoBack,
            modifier = Modifier
                .heightIn(min = Reach.touch)
                .testTag("calendar_prev")
                .semantics { contentDescription = previousLabel },
        ) {
            Text("‹", style = MaterialTheme.typography.headlineSmall)
        }
        TextButton(
            onClick = onOpenPicker,
            modifier = Modifier
                .heightIn(min = Reach.touch)
                .testTag("calendar_header")
                .semantics { contentDescription = pickLabel },
        ) {
            Text(
                "$title ▾",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
        }
        TextButton(
            onClick = onNext,
            enabled = canGoForward,
            modifier = Modifier
                .heightIn(min = Reach.touch)
                .testTag("calendar_next")
                .semantics { contentDescription = nextLabel },
        ) {
            Text("›", style = MaterialTheme.typography.headlineSmall)
        }
    }
}

/** Su to Sa, from strings. */
@Composable
private fun WeekdayRow() {
    val labels = listOf(
        R.string.calendar_weekday_sun,
        R.string.calendar_weekday_mon,
        R.string.calendar_weekday_tue,
        R.string.calendar_weekday_wed,
        R.string.calendar_weekday_thu,
        R.string.calendar_weekday_fri,
        R.string.calendar_weekday_sat,
    )
    Row(modifier = Modifier.fillMaxWidth()) {
        labels.forEach { id ->
            Text(
                stringResource(id),
                modifier = Modifier.weight(1f),
                textAlign = TextAlign.Center,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** Leading blanks, the month's days, trailing blanks. */
@Composable
private fun CalendarGrid(
    shown: YearMonth,
    byDate: Map<String, CalendarDayUi>,
    today: String?,
    onDay: (CalendarDayUi) -> Unit,
) {
    val leading = shown.leadingBlanks()
    val length = shown.lengthOfMonth()
    val rows = (leading + length + DAYS_IN_WEEK - 1) / DAYS_IN_WEEK
    Column {
        repeat(rows) { row ->
            Row(modifier = Modifier.fillMaxWidth()) {
                repeat(DAYS_IN_WEEK) { col ->
                    val dayNumber = row * DAYS_IN_WEEK + col - leading + 1
                    Box(modifier = Modifier.weight(1f), contentAlignment = Alignment.Center) {
                        if (dayNumber in 1..length) {
                            val date = shown.isoDay(dayNumber)
                            DayCell(dayNumber, byDate[date], date, date == today, onDay)
                        } else {
                            Box(modifier = Modifier.heightIn(min = Reach.touch))
                        }
                    }
                }
            }
        }
    }
}

/** One day: a plain number, or a tappable cell drawn by its server state. */
@Composable
private fun DayCell(
    number: Int,
    day: CalendarDayUi?,
    date: String,
    isToday: Boolean,
    onDay: (CalendarDayUi) -> Unit,
) {
    if (day == null) {
        Box(modifier = Modifier.size(Reach.touch), contentAlignment = Alignment.Center) {
            if (isToday) TodayRing(date)
            Text(
                number.toString(),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        return
    }
    val look = dayLook(day.state)
    val stateLabel = stringResource(stateLabelRes(day.state))
    val count = day.classes.size
    val countLabel =
        if (count > 1) {
            pluralStringResource(R.plurals.calendar_class_count, count, count.toString())
        } else {
            null
        }
    val described = stringResource(R.string.calendar_day_description, number.toString(), stateLabel)
    val description = if (countLabel != null) "$described, $countLabel" else described
    Box(
        modifier = Modifier
            .size(Reach.touch)
            .testTag(calendarDayTag(day.state, date))
            .semantics { contentDescription = description }
            .clickable { onDay(day) },
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(2.dp)
                .clip(cellShape)
                .background(look.background)
                .then(if (look.outline) Modifier.border(BorderStroke(1.5.dp, look.ink), cellShape) else Modifier),
            contentAlignment = Alignment.Center,
        ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (day.state == CalendarState.TAKEN) {
                        Text("✓", color = look.ink, style = MaterialTheme.typography.labelSmall)
                    }
                    Text(
                        number.toString(),
                        color = look.ink,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                        textDecoration = if (day.state == CalendarState.CANCELLED) TextDecoration.LineThrough else null,
                    )
                }
                if (day.state == CalendarState.UPCOMING) {
                    Box(
                        modifier = Modifier
                            .padding(top = MARKER_GAP.dp)
                            .size(DOT_SIZE.dp)
                            .clip(CircleShape)
                            .background(look.ink),
                    )
                }
            }
        }
        if (isToday) TodayRing(date)
        if (count > 1) {
            Text(
                count.toString(),
                color = look.ink,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(end = 3.dp)
                    .testTag("calendar_count_$date"),
            )
        }
    }
}

/**
 * The ring around the server's today, drawn over whatever the day's
 * state paints, so a recorded class keeps its tick and still reads as
 * today.
 *
 * @param date `YYYY-MM-DD`
 */
@Composable
private fun TodayRing(date: String) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .padding(1.dp)
            .border(BorderStroke(2.dp, MaterialTheme.colorScheme.primary), cellShape)
            .testTag(calendarTodayTag(date)),
    )
}

/** How a day state is painted. */
private data class DayLook(val background: Color, val ink: Color, val outline: Boolean)

@Composable
private fun dayLook(state: CalendarState): DayLook {
    val scheme = MaterialTheme.colorScheme
    val dark = scheme.surface.luminance() < HALF
    return when (state) {
        CalendarState.TAKEN ->
            DayLook(
                if (dark) GreenTintDark else GreenTintLight,
                if (dark) GreenInkDark else GreenInkLight,
                false,
            )
        CalendarState.TODAY ->
            DayLook(
                if (dark) GreenFillDark else GreenFillLight,
                if (dark) OnGreenFillDark else Color.White,
                false,
            )
        CalendarState.UPCOMING -> DayLook(Color.Transparent, scheme.primary, true)
        CalendarState.NOT_RECORDED -> DayLook(scheme.surfaceContainerHigh, scheme.onSurfaceVariant, false)
        CalendarState.CANCELLED -> DayLook(Color.Transparent, scheme.onSurfaceVariant, false)
    }
}

private fun stateLabelRes(state: CalendarState): Int = when (state) {
    CalendarState.TAKEN -> R.string.calendar_state_taken
    CalendarState.TODAY -> R.string.calendar_state_today
    CalendarState.UPCOMING -> R.string.calendar_state_upcoming
    CalendarState.NOT_RECORDED -> R.string.calendar_state_not_recorded
    CalendarState.CANCELLED -> R.string.calendar_state_cancelled
}

/** Month and year picker that offers only months inside the range. */
@Composable
private fun MonthPicker(
    shown: YearMonth,
    firstMonth: YearMonth,
    lastMonth: YearMonth,
    onPick: (YearMonth) -> Unit,
    onDismiss: () -> Unit,
) {
    var year by remember { mutableIntStateOf(shown.year) }
    val previousYear = stringResource(R.string.calendar_prev_year)
    val nextYear = stringResource(R.string.calendar_next_year)
    val months = (1..MONTHS_IN_YEAR).map { YearMonth(year, it) }.filter { it in firstMonth..lastMonth }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(R.string.calendar_picker_title)) },
        text = {
            Column {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    TextButton(
                        onClick = { year -= 1 },
                        enabled = year > firstMonth.year,
                        modifier = Modifier
                            .heightIn(min = Reach.touch)
                            .testTag("calendar_picker_prev_year")
                            .semantics { contentDescription = previousYear },
                    ) { Text("‹") }
                    Text(year.toString(), style = MaterialTheme.typography.titleMedium)
                    TextButton(
                        onClick = { year += 1 },
                        enabled = year < lastMonth.year,
                        modifier = Modifier
                            .heightIn(min = Reach.touch)
                            .testTag("calendar_picker_next_year")
                            .semantics { contentDescription = nextYear },
                    ) { Text("›") }
                }
                months.chunked(MONTHS_PER_ROW).forEach { rowMonths ->
                    Row(modifier = Modifier.fillMaxWidth()) {
                        repeat(MONTHS_PER_ROW) { index ->
                            val ym = rowMonths.getOrNull(index)
                            Box(modifier = Modifier.weight(1f), contentAlignment = Alignment.Center) {
                                if (ym != null) {
                                    TextButton(
                                        onClick = { onPick(ym) },
                                        modifier = Modifier
                                            .heightIn(min = Reach.touch)
                                            .testTag("calendar_picker_month_$ym"),
                                    ) {
                                        Text(
                                            monthName(ym.toString(), short = true),
                                            fontWeight = if (ym == shown) FontWeight.Bold else FontWeight.Normal,
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = Reach.touch)) {
                Text(stringResource(R.string.calendar_picker_close))
            }
        },
    )
}
