package com.shikkhokplus.app.feature.classcalendar

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.CalendarDayUi
import com.shikkhokplus.app.core.ui.CalendarMapper
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.Calendar

/**
 * Holds the Classes tab's month calendar.
 *
 * Holds no business logic [TC-9, D-31]: which days exist, their state
 * and whether a class may be recorded or planned all arrive from the
 * server. The only thing decided here is which month to ask for, and
 * the first is the phone's current one.
 *
 * @property repository Where months come from
 * @property currentMonth The month to open on; injectable for tests
 */
class ClassCalendarViewModel(
    private val repository: ClassCalendarRepository,
    private val currentMonth: () -> YearMonth = ::phoneMonth,
) : ViewModel() {

    private val _state = MutableStateFlow<ClassCalendarUiState>(ClassCalendarUiState.Idle)

    /** What the calendar renders. */
    val state: StateFlow<ClassCalendarUiState> = _state.asStateFlow()

    private val _target = MutableStateFlow<ClassTarget?>(null)

    /** The class screen to show, or null. */
    val target: StateFlow<ClassTarget?> = _target.asStateFlow()

    private var batchId: String? = null
    private var shown: YearMonth? = null

    /**
     * Open the calendar on the current month.
     *
     * @param batch The batch
     */
    fun load(batch: String) {
        batchId = batch
        read(currentMonth())
    }

    /**
     * Move to a month the person picked.
     *
     * @param month The month
     */
    fun pick(month: YearMonth) {
        read(month)
    }

    /** Read the month on screen again, e.g. after a save. */
    fun reload() {
        read(shown ?: return)
    }

    /** Try the last read again. */
    fun retry() {
        read(shown ?: currentMonth())
    }

    /**
     * A day was tapped.
     *
     * @param day The day
     */
    fun tapDay(day: CalendarDayUi) {
        _target.value = ClassTapRouter.forDay(day.classes)
    }

    /**
     * A class was chosen from a day's list.
     *
     * @param clazz The class
     */
    fun chooseClass(clazz: CalendarClassUi) {
        _target.value = ClassTapRouter.forClass(clazz)
    }

    /** Close whatever class screen is open. */
    fun closeTarget() {
        _target.value = null
    }

    private fun read(month: YearMonth) {
        val batch = batchId ?: return
        shown = month
        _state.value = ClassCalendarUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.month(batch, month.year, month.month)) {
                    is AuthResult.Ok -> ClassCalendarUiState.Loaded(CalendarMapper.toUi(result.value))
                    is AuthResult.Refused ->
                        ClassCalendarUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                    AuthResult.TransportFailure -> ClassCalendarUiState.Failed(OFFLINE_KEY, retryable = true)
                }
        }
    }

    companion object {
        /** The key shown when the server cannot be reached. */
        const val OFFLINE_KEY: String = "error.network.unreachable"

        /**
         * The month on this phone's clock.
         *
         * @return The current month
         */
        fun phoneMonth(): YearMonth {
            val now = Calendar.getInstance()
            return YearMonth(now.get(Calendar.YEAR), now.get(Calendar.MONTH) + 1)
        }
    }
}
