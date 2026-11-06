package com.shikkhokplus.app.feature.fees

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.FeeHistoryDto
import com.shikkhokplus.app.core.network.SeatExtraFeesDto
import com.shikkhokplus.app.core.network.PaymentReviewDto
import com.shikkhokplus.app.core.network.RecordPaymentBodyDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * Which lens is reading a fee history.
 *
 * **An enum rather than a boolean or a string**, so a `when` over it
 * fails to compile if a fourth reader ever appears rather than
 * silently taking one of the three existing routes.
 */
enum class FeeReader {
    /** The student reading their own seat. */
    STUDENT,

    /** A guardian reading their child's seat. */
    GUARDIAN,

    /** The teacher who owns the batch the seat sits in. */
    TEACHER,
}

/**
 * What the fee history screen needs from the network.
 */
interface FeesRepository {
    /**
     * Read the signed-in student's own history for one seat.
     *
     * @param enrollmentId The seat
     * @return The history, a refusal, or a transport failure
     */
    suspend fun myFees(enrollmentId: String): AuthResult<FeeHistoryDto>

    /**
     * Read one child's history, for their guardian.
     *
     * @param enrollmentId The child's seat
     * @return The history, a refusal, or a transport failure
     */
    suspend fun childFees(enrollmentId: String): AuthResult<FeeHistoryDto>

    /**
     * Read one seat's history, for its teacher.
     *
     * @param enrollmentId The seat
     * @return The history, a refusal, or a transport failure
     */
    suspend fun enrollmentFees(enrollmentId: String): AuthResult<FeeHistoryDto>

    /**
     * Read the exam and other fees one seat was charged. One route for
     * every lens; the server decides whether this caller may read it.
     *
     * @param enrollmentId The seat
     * @return The fees, a refusal, or a transport failure
     */
    suspend fun seatExtraFees(enrollmentId: String): AuthResult<SeatExtraFeesDto>
}

/**
 * What "Record payment" needs from the network: the teacher's write.
 *
 * Apart from [FeesRepository] because only the teacher's reader has it;
 * a student's or guardian's screen is built without one and so cannot
 * offer the action at all.
 */
interface RecordPaymentRepository {
    /**
     * Record money received by hand for one seat, approved in one step.
     *
     * @param enrollmentId The seat
     * @param body The amount, channel, reference, note and carry-or-waive
     * @return The recorded payment, a refusal, or a transport failure
     */
    suspend fun recordPayment(
        enrollmentId: String,
        body: RecordPaymentBodyDto,
    ): AuthResult<PaymentReviewDto>
}

/**
 * Holds the fee history screen's state. Holds no business logic
 * [TC-9, D-31].
 *
 * Every decision is delegated to [FeeStateMapper], including the
 * **total**, which the server computes: summing the rows here would
 * be money arithmetic on the client [D-20].
 *
 * **"Record payment"** is the teacher's: the sheet opens at the
 * server's total, the server settles the money, and on success the
 * history is read again so what shows is what was recorded. A failed
 * send keeps the sheet and its retry key, so the teacher's resend is
 * one the server can replay.
 *
 * @property repository The three history reads
 * @property recorder The teacher's write, or null for a family reader
 * @property newMutationId Generates a record's replay key; injectable
 *   so a test can name it
 */
class FeesViewModel(
    private val repository: FeesRepository,
    private val recorder: RecordPaymentRepository? = null,
    private val newMutationId: () -> String = { UUID.randomUUID().toString() },
) : ViewModel() {

    private val _state = MutableStateFlow<FeeUiState>(FeeUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<FeeUiState> = _state.asStateFlow()

    private val _sheet = MutableStateFlow<RecordSheet?>(null)

    /** The open "Record payment" sheet, or null. */
    val sheet: StateFlow<RecordSheet?> = _sheet.asStateFlow()

    private val _recorded = MutableStateFlow(false)

    /** True once a record was accepted, until the sheet is opened again. */
    val recorded: StateFlow<Boolean> = _recorded.asStateFlow()

    private val _extraFees = MutableStateFlow<List<ExtraFeeRow>>(emptyList())

    /**
     * The seat's exam and other fees. Read beside the monthly history and
     * shown only when the read succeeds: a failure here hides a section
     * rather than failing the screen the monthly fees already fill.
     */
    val extraFees: StateFlow<List<ExtraFeeRow>> = _extraFees.asStateFlow()

    /** Whether this screen may offer "Record payment" at all. */
    val canRecord: Boolean get() = recorder != null

    private var lastAction: (() -> Unit)? = null
    private var seat: String? = null
    private var lastReader: FeeReader? = null

    /**
     * Load one seat's history through the reader's own route.
     *
     * @param enrollmentId The seat to read
     * @param reader Which lens is asking
     */
    fun load(
        enrollmentId: String,
        reader: FeeReader,
    ) {
        lastAction = { load(enrollmentId, reader) }
        seat = enrollmentId
        lastReader = reader
        _state.value = FeeUiState.Loading
        viewModelScope.launch {
            val extra = repository.seatExtraFees(enrollmentId)
            _extraFees.value =
                (extra as? AuthResult.Ok)?.value?.fees.orEmpty().map {
                    ExtraFeeRow(it.extraFeeId, it.label, it.owed, it.dueOn, it.status)
                }
        }
        viewModelScope.launch {
            val result =
                when (reader) {
                    FeeReader.STUDENT -> repository.myFees(enrollmentId)
                    FeeReader.GUARDIAN -> repository.childFees(enrollmentId)
                    FeeReader.TEACHER -> repository.enrollmentFees(enrollmentId)
                }
            _state.value =
                when (result) {
                    is AuthResult.Ok ->
                        FeeStateMapper.afterLoad(
                            cycles = result.value.cycles,
                            // The SERVER's total, never a sum of the
                            // rows above it.
                            totalOutstanding = result.value.totalOutstanding,
                            monthStates = result.value.monthStates,
                        )

                    is AuthResult.Refused -> FeeStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure -> FeeStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Retry, when the person asks.
     *
     * Never automatic: V1 has no local queue [TC-8, D-9].
     */
    fun retry() {
        lastAction?.invoke()
    }

    /**
     * Open "Record payment" at what the server says the seat owes.
     *
     * A seat with nothing charged yet opens blank; any amount recorded
     * there is held as credit by the server.
     */
    fun openRecord() {
        if (recorder == null) return
        val owed = (_state.value as? FeeUiState.Loaded)?.totalOutstanding ?: Money.ZERO
        _recorded.value = false
        _sheet.value = RecordSheet.open(owed, newMutationId())
    }

    /**
     * Type the amount received. A carry-or-waive that no longer applies
     * to the new amount is dropped.
     *
     * @param typed The text as typed
     */
    fun typeRecordAmount(typed: String) {
        val sheet = _sheet.value ?: return
        val next = sheet.copy(typed = typed, errorKey = null)
        _sheet.value = if (next.side == sheet.side) next else next.copy(disposition = null)
    }

    /**
     * Choose how the money arrived.
     *
     * @param channel `cash` or a mobile service
     */
    fun chooseRecordChannel(channel: String) {
        if (channel !in RecordSheet.CHANNELS) return
        _sheet.value = _sheet.value?.copy(channel = channel)
    }

    /**
     * Type the reference.
     *
     * @param reference A transaction id or receipt number
     */
    fun typeRecordReference(reference: String) {
        _sheet.value = _sheet.value?.copy(reference = reference.take(RecordSheet.REFERENCE_MAX))
    }

    /**
     * Type the note shown to the family.
     *
     * @param note The note
     */
    fun typeRecordNote(note: String) {
        _sheet.value = _sheet.value?.copy(note = note.take(RecordSheet.NOTE_MAX))
    }

    /**
     * Choose carry forward or waive for a short amount.
     *
     * @param disposition `carried` or `waived`
     */
    fun chooseRecordDisposition(disposition: String) {
        _sheet.value = _sheet.value?.copy(disposition = disposition)
    }

    /** Close the sheet without recording anything. */
    fun dismissRecord() {
        _sheet.value = null
    }

    /**
     * Send the record, once everything it needs is supplied.
     *
     * On success the sheet closes and the history is read again. On a
     * refusal or a lost connection the sheet stays, showing why, with
     * the same retry key, so pressing Record again is a replay.
     */
    fun confirmRecord() {
        val writer = recorder ?: return
        val enrollmentId = seat ?: return
        val sheet = _sheet.value ?: return
        val body = sheet.body() ?: return
        _sheet.value = sheet.copy(busy = true, errorKey = null)
        viewModelScope.launch {
            when (val result = writer.recordPayment(enrollmentId, body)) {
                is AuthResult.Ok -> {
                    _sheet.value = null
                    _recorded.value = true
                    lastReader?.let { load(enrollmentId, it) }
                }
                is AuthResult.Refused ->
                    _sheet.value = _sheet.value?.copy(busy = false, errorKey = result.envelope.error.messageKey)
                AuthResult.TransportFailure ->
                    _sheet.value = _sheet.value?.copy(busy = false, errorKey = FeeStateMapper.OFFLINE_KEY)
            }
        }
    }
}
