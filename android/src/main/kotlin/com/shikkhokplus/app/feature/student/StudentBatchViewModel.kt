package com.shikkhokplus.app.feature.student

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.network.StudentBatchDto
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.CalendarMapper
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarUiState
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Holds S2's state: one batch from the student's or a guardian's side.
 *
 * Three reads, in order, and the first failure is the result: a half-
 * loaded batch would show a fee with no classes, or classes with no
 * fee, and either reads as the whole truth.
 *
 * The Classes tab's month is a fourth read, kept apart: a month that
 * fails to load never hides the fee or the notices.
 *
 * @property repository The student's reads
 * @property currentMonth The month to open on; injectable for tests
 */
class StudentBatchViewModel(
    private val repository: StudentRepository,
    private val currentMonth: () -> YearMonth = { ClassCalendarViewModel.phoneMonth() },
) : ViewModel() {

    private val _state = MutableStateFlow<StudentBatchUiState>(StudentBatchUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<StudentBatchUiState> = _state.asStateFlow()

    private val _tab = MutableStateFlow(FamilyTab.CLASSES)

    /** The open tab, which survives the screen being rebuilt. */
    val tab: StateFlow<FamilyTab> = _tab.asStateFlow()

    private val _calendar = MutableStateFlow<ClassCalendarUiState>(ClassCalendarUiState.Idle)

    /** The Classes tab's month. */
    val calendar: StateFlow<ClassCalendarUiState> = _calendar.asStateFlow()

    private var lastSeat: String? = null
    private var shown: YearMonth? = null

    /**
     * Load one batch, and its calendar on the month already shown if
     * this seat is the one it was showing.
     *
     * @param enrollmentId The student's own seat
     * @param month The month to open on if none is kept; the phone's
     *   current one when null
     */
    fun load(enrollmentId: String, month: YearMonth? = null) {
        val keep = shown.takeIf { lastSeat == enrollmentId }
        lastSeat = enrollmentId
        _state.value = StudentBatchUiState.Loading
        viewModelScope.launch { _state.value = read(enrollmentId) }
        readMonth(enrollmentId, keep ?: month ?: currentMonth())
    }

    /**
     * Move the calendar to a month the person picked.
     *
     * @param month The month
     */
    fun pickMonth(month: YearMonth) {
        lastSeat?.let { readMonth(it, month) }
    }

    /** Read the shown month again, only when asked [TC-8, D-9]. */
    fun retryMonth() {
        lastSeat?.let { readMonth(it, shown ?: currentMonth()) }
    }

    /**
     * A class of the loaded month, for its detail.
     *
     * @param sessionId The class
     * @return The class, or null if the month is not loaded or lacks it
     */
    fun classOf(sessionId: String): CalendarClassUi? =
        (_calendar.value as? ClassCalendarUiState.Loaded)
            ?.view
            ?.days
            ?.flatMap { it.classes }
            ?.firstOrNull { it.sessionId == sessionId }

    private fun readMonth(seat: String, month: YearMonth) {
        shown = month
        _calendar.value = ClassCalendarUiState.Loading
        viewModelScope.launch {
            _calendar.value =
                when (val result = repository.month(seat, month.year, month.month)) {
                    is AuthResult.Ok -> ClassCalendarUiState.Loaded(CalendarMapper.toUi(result.value))
                    is AuthResult.Refused ->
                        ClassCalendarUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                    AuthResult.TransportFailure ->
                        ClassCalendarUiState.Failed(StudentStateMapper.OFFLINE_KEY, retryable = true)
                }
        }
    }

    /**
     * Open a tab.
     *
     * @param tab The tab to show
     */
    fun select(tab: FamilyTab) {
        _tab.value = tab
    }

    /**
     * Load a seat only if this model has not already, for a detail
     * screen that may be the first to build it.
     *
     * @param enrollmentId The seat
     * @param month The month to load the calendar on if nothing is kept
     */
    fun ensureLoaded(enrollmentId: String, month: YearMonth? = null) {
        if (lastSeat != enrollmentId) load(enrollmentId, month)
    }

    /** Repeat the load, only when asked [TC-8, D-9]. */
    fun retry() {
        lastSeat?.let(::load)
    }

    /**
     * Make the three reads and combine them.
     *
     * @param seat The student's own seat
     * @return The state to show
     */
    private suspend fun read(seat: String): StudentBatchUiState {
        val batches =
            when (val result = repository.batches()) {
                is AuthResult.Ok -> result.value
                else -> return failed(result)
            }
        val batch = batches.firstOrNull { it.enrollmentId == seat } ?: return StudentStateMapper.notFound()
        return readSeat(batch)
    }

    /**
     * Read one seat's classes and results, after its row was found.
     *
     * @param batch The seat's row from the student's own list
     * @return The state to show
     */
    private suspend fun readSeat(batch: StudentBatchDto): StudentBatchUiState {
        val view =
            when (val result = repository.batchView(batch.enrollmentId)) {
                is AuthResult.Ok -> result.value
                else -> return failed(result)
            }
        // The header's fee is the view's: the server's line for this seat,
        // for a guardian as for a student, never one picked from a list.
        val seat = batch.copy(currentFee = view.currentFee ?: batch.currentFee)
        // A refusal here is the teacher hiding marksheets from families:
        // the page still shows, with no results, rather than failing whole.
        return when (val result = repository.progress(batch.enrollmentId)) {
            is AuthResult.Ok -> StudentStateMapper.afterBatch(seat, view, result.value)
            is AuthResult.Refused -> StudentStateMapper.afterBatch(seat, view, emptyList())
            AuthResult.TransportFailure -> failed(result)
        }
    }

    /**
     * Name a failed read.
     *
     * @param result A refusal or a transport failure
     * @return The failure to show
     */
    private fun failed(result: AuthResult<*>): StudentBatchUiState =
        when (result) {
            is AuthResult.Refused -> {
                val (key, retryable) = StudentStateMapper.failure(result.envelope)
                StudentBatchUiState.Failed(key, retryable)
            }
            else -> StudentBatchUiState.Failed(StudentStateMapper.OFFLINE_KEY, retryable = true)
        }
}
