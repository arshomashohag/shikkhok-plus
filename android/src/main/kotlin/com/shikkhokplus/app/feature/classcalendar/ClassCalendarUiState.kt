package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.MonthViewUi

/** What the Classes tab's calendar renders. */
sealed interface ClassCalendarUiState {
    /** Nothing asked for yet. */
    data object Idle : ClassCalendarUiState

    /** A month is being read. */
    data object Loading : ClassCalendarUiState

    /**
     * A month is on screen.
     *
     * @property view The month to draw
     */
    data class Loaded(val view: MonthViewUi) : ClassCalendarUiState

    /**
     * The month could not be read.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : ClassCalendarUiState
}

/** Where tapping a class leads, decided by the server's flags. */
sealed interface ClassTarget {
    /**
     * Record the class: topics, notes and attendance.
     *
     * @property clazz The class
     */
    data class Record(val clazz: CalendarClassUi) : ClassTarget

    /**
     * Plan the class's topics before it starts.
     *
     * @property clazz The class
     */
    data class Plan(val clazz: CalendarClassUi) : ClassTarget

    /**
     * Read the class; the server allows neither writing nor planning.
     *
     * @property clazz The class
     */
    data class ReadOnly(val clazz: CalendarClassUi) : ClassTarget

    /**
     * Several classes on one day: choose one first.
     *
     * @property classes The day's classes, in the server's order
     */
    data class Choose(val classes: List<CalendarClassUi>) : ClassTarget
}

/** Turns a tap into a destination without deciding anything itself. */
object ClassTapRouter {

    /**
     * Route one class by what the server says the teacher may do.
     *
     * `recordable` wins over `plannable`; neither means read-only. The
     * class's date and state are never consulted.
     *
     * @param clazz The class tapped
     * @return Where it opens
     */
    fun forClass(clazz: CalendarClassUi): ClassTarget =
        when {
            clazz.recordable -> ClassTarget.Record(clazz)
            clazz.plannable -> ClassTarget.Plan(clazz)
            else -> ClassTarget.ReadOnly(clazz)
        }

    /**
     * Route a tapped day.
     *
     * @param classes The day's classes
     * @return The class's destination, a list when there are several,
     *   or null for a day with none
     */
    fun forDay(classes: List<CalendarClassUi>): ClassTarget? =
        when (classes.size) {
            0 -> null
            1 -> forClass(classes.single())
            else -> ClassTarget.Choose(classes)
        }
}
