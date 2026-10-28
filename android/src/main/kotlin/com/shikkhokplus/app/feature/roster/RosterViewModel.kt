package com.shikkhokplus.app.feature.roster

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.RosterRowDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * One roster read, with the batch name the screen titles itself with.
 *
 * @property batchName Which class this is
 * @property rows The seats, in the order the server returned them
 * @property fetchedAtLabel When this came from cache, or null when live
 * @property acceptedCount How many seats at least one link accepted, as
 *   the SERVER counted them [BR1.2, BR1.3], or null when this read did
 *   not carry the batch summary.
 *
 *   Carried here rather than counted from [rows], which is the whole
 *   point: a client tally is the client deciding what counts as
 *   accepted, and it is wrong the moment the roster paginates
 *   [NFR20.9].
 * @property seatCount The denominator, counting every seat the teacher
 *   created including declined ones [BR1.4]
 */
data class RosterPayload(
    val batchName: String,
    val rows: List<RosterRowDto>,
    val fetchedAtLabel: String? = null,
    val acceptedCount: Int? = null,
    val seatCount: Int? = null,
)

/** What the roster repository must provide. */
interface RosterRepository {
    /**
     * Read one batch's roster.
     *
     * @param batchId The batch whose roster to read
     * @return The roster, an error envelope, or a transport failure
     */
    suspend fun roster(batchId: String): AuthResult<RosterPayload>

    /**
     * Remove a dormant, never-erased seat.
     *
     * @param enrollmentId The seat to remove
     * @return Nothing on success, or why the server refused
     */
    suspend fun removeEnrollment(enrollmentId: String): AuthResult<Unit>

    /**
     * Add a student to a batch.
     *
     * @param batchId The batch to add to
     * @param displayName The teacher-typed name
     * @param guardianPhone The guardian's number, or null
     * @param feeAmount This seat's fee as a canonical string, or null
     *   to inherit the batch default
     * @return Nothing on success, or why the server refused
     */
    suspend fun addEnrollment(
        batchId: String,
        displayName: String,
        guardianPhone: String?,
        feeAmount: String?,
    ): AuthResult<Unit>
}

/**
 * Holds the roster screen's state. Holds no business logic [TC-9, D-31].
 *
 * Every decision is delegated to [RosterStateMapper], which is the unit
 * the tests target. This class owns the coroutine and the state holder
 * and nothing else.
 *
 * **V1 accepts no write without connectivity** [TC-8, D-9]. A failed
 * removal surfaces [RosterUiState.Failed] with an explicit retry
 * affordance; it is never queued locally and never appears to have
 * succeeded. The last attempted removal is remembered **only** so
 * [retry] can repeat it when the user asks.
 */
class RosterViewModel(
    private val repository: RosterRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<RosterUiState>(RosterUiState.Idle)

    /** What the screen renders. */
    val state: StateFlow<RosterUiState> = _state.asStateFlow()

    private val _writeState = MutableStateFlow<WriteState>(WriteState.Idle)

    /**
     * Where the add-student form's write stands, apart from the roster.
     *
     * The form closes only on [WriteState.Saved]. See [WriteState] for
     * the race this replaces.
     */
    val writeState: StateFlow<WriteState> = _writeState.asStateFlow()

    private var lastBatchId: String? = null

    // The roster endpoint does not return the batch name, and the
    // teacher already knows which class they tapped -- so the caller
    // supplies it rather than the client asking the server something it
    // was just told.
    private var lastBatchName: String = ""
    private var pendingRemoval: String? = null

    // The row a removal is in flight for, so `retry` can repeat it as a
    // removal carrying its remedy rather than as a bare id.
    private var removingRow: RosterRow? = null

    /**
     * Load a batch's roster.
     *
     * @param batchId The batch whose roster to read
     */
    fun load(batchId: String, batchName: String = "") {
        lastBatchId = batchId
        lastBatchName = batchName
        pendingRemoval = null
        _state.value = RosterUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.roster(batchId)) {
                    is AuthResult.Ok ->
                        RosterStateMapper.afterLoad(
                            batchName = result.value.batchName.ifBlank { lastBatchName },
                            rows = result.value.rows,
                            fetchedAtLabel = result.value.fetchedAtLabel,
                            // Both from the server or neither: a
                            // numerator formatted against a
                            // denominator the client supplied would be
                            // a count nobody computed [BR1.3].
                            accepted =
                                result.value.acceptedCount?.let { taken ->
                                    result.value.seatCount?.let { total ->
                                        AcceptedCount(taken, total)
                                    }
                                },
                        )
                    is AuthResult.Refused -> RosterStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure -> RosterStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Ask the teacher to confirm, naming the seat [W4].
     *
     * @param row The seat the teacher chose to remove
     */
    fun confirmRemoval(row: RosterRow) {
        removingRow = row
        _state.value = RosterStateMapper.beforeRemoval(row)
    }

    /** Abandon a removal and return to the roster. */
    fun cancelRemoval() {
        removingRow = null
        pendingRemoval = null
        lastBatchId?.let { load(it, lastBatchName) }
    }

    /** Dismiss a refusal and return to the roster. */
    fun dismissRefusal() = cancelRemoval()

    /**
     * Remove a seat, reloading the roster when the server accepts.
     *
     * **A refusal carries its remedy** [BR3.2]. The server returns two
     * codes because the remedies differ, and routing both through
     * `afterError` would render one message for both -- leaving a
     * teacher trying the remedy that cannot work. That is the gap this
     * unit closes, and it is why the refusal path is separate from the
     * generic one.
     *
     * @param row The seat to remove
     */
    fun remove(row: RosterRow) {
        removingRow = row
        pendingRemoval = row.enrollmentId
        _state.value = RosterUiState.Loading
        viewModelScope.launch {
            when (val result = repository.removeEnrollment(row.enrollmentId)) {
                is AuthResult.Ok -> {
                    pendingRemoval = null
                    removingRow = null
                    lastBatchId?.let { load(it, lastBatchName) }
                }
                is AuthResult.Refused ->
                    _state.value =
                        RosterStateMapper.afterRemovalRefused(row, result.envelope)
                AuthResult.TransportFailure ->
                    _state.value = RosterStateMapper.afterTransportFailure()
            }
        }
    }

    /**
     * Add a student, then reload the roster.
     *
     * **No optimistic insert**, for the same reason removal has no
     * local queue [TC-8, D-9].
     *
     * **The outcome goes to [writeState], and the roster is left
     * alone**, for the reason [BatchesViewModel.create] gives: the
     * form used to navigate away before the server answered, the
     * roster reloaded concurrently, and a refused add could be
     * overwritten by the old list with no error shown.
     *
     * A second tap while one is in flight is ignored, so a slow network
     * cannot add the same student twice.
     *
     * @param displayName The teacher-typed name
     * @param guardianPhone The guardian's number, or null
     * @param feeAmount This seat's fee in canonical form, or null to
     *   inherit
     */
    fun addStudent(
        displayName: String,
        guardianPhone: String?,
        feeAmount: String?,
    ) {
        val batchId = lastBatchId ?: return
        if (_writeState.value == WriteState.Saving) return
        _writeState.value = WriteState.Saving
        viewModelScope.launch {
            _writeState.value =
                when (
                    val result =
                        repository.addEnrollment(batchId, displayName, guardianPhone, feeAmount)
                ) {
                    is AuthResult.Ok -> {
                        load(batchId, lastBatchName)
                        WriteState.Saved
                    }
                    is AuthResult.Refused ->
                        WriteState.Failed(
                            messageKey = result.envelope.error.messageKey,
                            retryable = result.envelope.error.retryable,
                        )
                    AuthResult.TransportFailure ->
                        WriteState.Failed(
                            messageKey = RosterStateMapper.OFFLINE_KEY,
                            retryable = true,
                        )
                }
        }
    }

    /**
     * Mark a finished write as seen, so the form does not close twice.
     *
     * Called by the route once it has acted on [WriteState.Saved], and
     * when the form is abandoned, so the next form opens clean.
     */
    fun acknowledgeWrite() {
        if (_writeState.value != WriteState.Saving) _writeState.value = WriteState.Idle
    }

    /**
     * Repeat whatever last failed, and only when the user asks.
     *
     * A removal that failed is retried as a removal rather than
     * degrading into a reload, which would silently drop the user's
     * intent and leave the seat in place with no error on screen.
     */
    fun retry() {
        val removal = removingRow
        if (removal != null) {
            remove(removal)
            return
        }
        lastBatchId?.let { load(it, lastBatchName) }
    }
}
