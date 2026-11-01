package com.shikkhokplus.app.core.ui

import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.network.CalendarClassDto
import com.shikkhokplus.app.core.network.CalendarDayDto
import com.shikkhokplus.app.core.network.MonthViewDto

/**
 * What a calendar day or class looks like, as the server decided.
 *
 * @property wire The server's word for it
 */
enum class CalendarState(val wire: String) {
    TAKEN("taken"),
    TODAY("today"),
    UPCOMING("upcoming"),
    NOT_RECORDED("not_recorded"),
    CANCELLED("cancelled"),
    ;

    companion object {
        /**
         * Read the server's word.
         *
         * @param wire The `state` string
         * @return The state, or null if this build does not know it
         */
        fun fromWire(wire: String): CalendarState? = entries.firstOrNull { it.wire == wire }
    }
}

/**
 * A student's standing in one class.
 *
 * @property wire The server's word for it
 */
enum class CalendarMark(val wire: String) {
    PRESENT("present"),
    ABSENT("absent"),
    NOT_MARKED("not_marked"),
    NOT_ENROLLED("not_enrolled"),
    ;

    companion object {
        /**
         * Read the server's word.
         *
         * @param wire The `mark` string
         * @return The mark, or null if absent or unknown
         */
        fun fromWire(wire: String?): CalendarMark? = entries.firstOrNull { it.wire == wire }
    }
}

/**
 * One class on a calendar day.
 *
 * @property sessionId The class
 * @property date `YYYY-MM-DD`
 * @property startTime `HH:MM:SS`
 * @property endTime `HH:MM:SS`, if any
 * @property subjectName The subject, if any
 * @property state The class's state
 * @property topic The planned topic, if any
 * @property notes The teacher's notes, if any
 * @property plannable Whether the viewer may plan it
 * @property recordable Whether the viewer may record it
 * @property mark A student's standing, if the view carries one
 */
data class CalendarClassUi(
    val sessionId: String,
    val date: String,
    val startTime: String,
    val endTime: String?,
    val subjectName: String?,
    val state: CalendarState,
    val topic: String?,
    val notes: String?,
    val plannable: Boolean,
    val recordable: Boolean,
    val mark: CalendarMark?,
)

/**
 * One day that has classes.
 *
 * @property date `YYYY-MM-DD`
 * @property state The day's state
 * @property classes The classes that day
 */
data class CalendarDayUi(
    val date: String,
    val state: CalendarState,
    val classes: List<CalendarClassUi>,
) {
    /** The day of the month, e.g. 5 for `2026-11-05`; 0 if unreadable. */
    val dayOfMonth: Int get() = date.takeLast(DAY_DIGITS).toIntOrNull() ?: 0

    private companion object {
        const val DAY_DIGITS = 2
    }
}

/**
 * A month ready to draw.
 *
 * @property month The month shown
 * @property firstMonth Earliest month offered
 * @property lastMonth Latest month offered
 * @property days Days with classes
 */
data class MonthViewUi(
    val month: YearMonth,
    val firstMonth: YearMonth,
    val lastMonth: YearMonth,
    val days: List<CalendarDayUi>,
)

/** Turns the wire month into the model the calendar draws. */
object CalendarMapper {

    /**
     * Map a month response.
     *
     * A day or class whose state this build does not know is dropped,
     * never an error [D-26]. An unreadable bound falls back to the
     * month itself.
     *
     * @param dto The response
     * @return The month to draw
     */
    fun toUi(dto: MonthViewDto): MonthViewUi {
        val shown = YearMonth(dto.year, dto.month)
        return MonthViewUi(
            month = shown,
            firstMonth = YearMonth.parseOrNull(dto.firstMonth) ?: shown,
            lastMonth = YearMonth.parseOrNull(dto.lastMonth) ?: shown,
            days = dto.days.mapNotNull(::day),
        )
    }

    /**
     * Map one day.
     *
     * @param dto The day
     * @return The day, or null if its state is unknown
     */
    fun day(dto: CalendarDayDto): CalendarDayUi? {
        val state = CalendarState.fromWire(dto.state) ?: return null
        return CalendarDayUi(dto.date, state, dto.classes.mapNotNull(::calendarClass))
    }

    /**
     * Map one class.
     *
     * @param dto The class
     * @return The class, or null if its state is unknown
     */
    fun calendarClass(dto: CalendarClassDto): CalendarClassUi? {
        val state = CalendarState.fromWire(dto.state) ?: return null
        return CalendarClassUi(
            sessionId = dto.sessionId,
            date = dto.date,
            startTime = dto.startTime,
            endTime = dto.endTime,
            subjectName = dto.subjectName,
            state = state,
            topic = dto.topic,
            notes = dto.notes,
            plannable = dto.plannable,
            recordable = dto.recordable,
            mark = CalendarMark.fromWire(dto.mark),
        )
    }
}
