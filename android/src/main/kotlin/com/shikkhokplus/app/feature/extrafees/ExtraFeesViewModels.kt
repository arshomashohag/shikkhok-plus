package com.shikkhokplus.app.feature.extrafees

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.format.dhakaTodayIso
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ExtraFeeRaiseRequestDto
import com.shikkhokplus.app.core.network.ExtraFeeStudentDto
import com.shikkhokplus.app.core.network.SeatAmountDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.fees.RecordPaymentRepository
import com.shikkhokplus.app.feature.fees.RecordSheet
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

/** The message key for a request that never got an answer. */
internal const val OFFLINE_KEY: String = "error.network.unreachable"

/** The longest fee name the server stores. */
internal const val FEE_LABEL_MAX: Int = 80

/**
 * Holds a batch's list of exam and other fees. Every figure is the
 * server's [TC-9, D-31].
 *
 * @property repository The network
 */
class ExtraFeesViewModel(
    private val repository: ExtraFeesRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<ExtraFeesUiState>(ExtraFeesUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<ExtraFeesUiState> = _state.asStateFlow()

    private var batchId: String? = null

    /**
     * Read the batch's fees.
     *
     * @param batchId The batch
     */
    fun load(batchId: String) {
        this.batchId = batchId
        _state.value = ExtraFeesUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.batchFees(batchId)) {
                    is AuthResult.Ok -> ExtraFeesUiState.Loaded(result.value.fees)
                    is AuthResult.Refused ->
                        ExtraFeesUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
                    AuthResult.TransportFailure -> ExtraFeesUiState.Failed(OFFLINE_KEY, retryable = true)
                }
        }
    }

    /** Read again after a failure, when the person asks. */
    fun retry() {
        batchId?.let(::load)
    }
}

/**
 * Holds the raise-a-fee form.
 *
 * Validation here is format only: a name, an amount that parses, and at
 * least one student reached. **One retry key per opened form**, so a
 * raise sent again after a timeout is a replay, never a second fee.
 *
 * @property repository The network
 * @param today The default due date, overridden by tests
 * @param mutationId The retry key, overridden by tests
 */
class RaiseFeeViewModel(
    private val repository: ExtraFeesRepository,
    today: String = dhakaTodayIso(),
    private val mutationId: String = UUID.randomUUID().toString(),
) : ViewModel() {

    private val _state = MutableStateFlow(RaiseFeeUiState(dueOn = today))

    /** What the form renders. */
    val state: StateFlow<RaiseFeeUiState> = _state.asStateFlow()

    private var batchId: String? = null

    /**
     * Read who the fee could charge, and the batch's exams.
     *
     * The exams are a convenience: when they cannot be read the fee can
     * still be raised, unlinked, so a failure there hides the choice.
     *
     * @param batchId The batch
     */
    fun load(batchId: String) {
        this.batchId = batchId
        _state.update { it.copy(loading = true, loadFailedKey = null) }
        viewModelScope.launch {
            val exams =
                (repository.exams(batchId) as? AuthResult.Ok)?.value.orEmpty()
                    .filter { !it.cancelled }
                    .map { RaiseExam(it.examId, it.title) }
            when (val result = repository.batchFees(batchId)) {
                is AuthResult.Ok ->
                    _state.update {
                        it.copy(
                            loading = false,
                            students =
                                result.value.chargeableStudents.map { s ->
                                    RaiseStudent(s.enrollmentId, s.displayName)
                                },
                            exams = exams,
                        )
                    }
                is AuthResult.Refused ->
                    _state.update { it.copy(loading = false, loadFailedKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(loading = false, loadFailedKey = OFFLINE_KEY) }
            }
        }
    }

    /** Read the students again after a failure. */
    fun retry() {
        batchId?.let(::load)
    }

    /**
     * Choose exam or other; an other fee is linked to no exam.
     *
     * @param kind The kind
     */
    fun kind(kind: FeeKind) =
        _state.update {
            it.copy(kind = kind, examId = it.examId.takeIf { kind == FeeKind.EXAM }, failureKey = null)
        }

    /**
     * Name the fee.
     *
     * @param text The name families see
     */
    fun label(text: String) = _state.update { it.copy(label = text.take(FEE_LABEL_MAX), failureKey = null) }

    /**
     * Link the fee to an exam, or to none.
     *
     * @param examId The exam, or null
     */
    fun exam(examId: String?) =
        _state.update { form ->
            if (examId != null && form.exams.none { it.examId == examId }) return@update form
            form.copy(examId = examId, failureKey = null)
        }

    /**
     * Type the amount per student.
     *
     * @param text The amount as typed
     */
    fun amount(text: String) = _state.update { it.copy(typedAmount = text, failureKey = null) }

    /**
     * Pick the due date.
     *
     * @param isoDate `yyyy-MM-dd`
     */
    fun dueOn(isoDate: String) = _state.update { it.copy(dueOn = isoDate, failureKey = null) }

    /**
     * Charge, waive or leave out one student.
     *
     * @param enrollmentId The seat
     * @param choice What happens to them
     */
    fun choose(enrollmentId: String, choice: SeatChoice) =
        _state.update { form ->
            if (form.students.none { it.enrollmentId == enrollmentId }) return@update form
            val next =
                if (choice == SeatChoice.CHARGE) {
                    form.choices - enrollmentId
                } else {
                    form.choices + (enrollmentId to choice)
                }
            form.copy(choices = next, failureKey = null)
        }

    /** Send the form, when it can be sent. */
    fun raise() {
        val form = _state.value
        val batch = batchId ?: return
        if (!form.canRaise) return
        val amount = Money.fromTyped(form.typedAmount) ?: return
        val request =
            ExtraFeeRaiseRequestDto(
                purpose = form.kind.wire,
                label = form.label.trim(),
                examId = form.examId.takeIf { form.kind == FeeKind.EXAM },
                amount = amount,
                dueOn = form.dueOn,
                seatAmounts =
                    form.choices.filterValues { it == SeatChoice.WAIVE }.keys.map { SeatAmountDto(it, Money.ZERO) },
                excludedEnrollmentIds = form.choices.filterValues { it == SeatChoice.LEAVE_OUT }.keys.toList(),
                clientMutationId = mutationId,
            )
        _state.update { it.copy(saving = true, failureKey = null) }
        viewModelScope.launch {
            when (val result = repository.raise(batch, request)) {
                is AuthResult.Ok -> _state.update { it.copy(saving = false, raised = result.value) }
                is AuthResult.Refused ->
                    _state.update { it.copy(saving = false, failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(saving = false, failureKey = OFFLINE_KEY) }
            }
        }
    }
}

/**
 * Holds one fee's page and recording cash against it for one student.
 *
 * The record is the teacher's own "Record payment", tagged with the fee,
 * so the server settles it on the fee's ledger and never on a month.
 *
 * @property repository The fee reads
 * @property recorder The record write
 * @property newMutationId Generates a record's retry key
 */
class ExtraFeeDetailViewModel(
    private val repository: ExtraFeesRepository,
    private val recorder: RecordPaymentRepository,
    private val newMutationId: () -> String = { UUID.randomUUID().toString() },
) : ViewModel() {

    private val _state = MutableStateFlow<ExtraFeeDetailUiState>(ExtraFeeDetailUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<ExtraFeeDetailUiState> = _state.asStateFlow()

    private val _sheet = MutableStateFlow<RecordSheet?>(null)

    /** The open record sheet, or null. */
    val sheet: StateFlow<RecordSheet?> = _sheet.asStateFlow()

    private val _recorded = MutableStateFlow(false)

    /** True once a record was accepted, until a sheet is opened again. */
    val recorded: StateFlow<Boolean> = _recorded.asStateFlow()

    private var feeId: String? = null
    private var recordingFor: String? = null

    /**
     * Read the fee.
     *
     * @param extraFeeId The fee
     */
    fun load(extraFeeId: String) {
        feeId = extraFeeId
        viewModelScope.launch { _state.value = read(extraFeeId) }
    }

    /** Read again after a failure, when the person asks. */
    fun retry() {
        val id = feeId ?: return
        _state.value = ExtraFeeDetailUiState.Loading
        load(id)
    }

    /**
     * Open "Record payment" for one student at what they owe on the fee,
     * as the server says.
     *
     * @param student The student
     */
    fun openRecord(student: ExtraFeeStudentDto) {
        val fee = (_state.value as? ExtraFeeDetailUiState.Loaded)?.fee ?: return
        recordingFor = student.enrollmentId
        _recorded.value = false
        _sheet.value = RecordSheet.open(student.owed, newMutationId(), extraFeeId = fee.extraFeeId)
    }

    /**
     * Type the amount received; a carry-or-waive that no longer applies is dropped.
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
     * @param channel Cash or a mobile service
     */
    fun chooseRecordChannel(channel: String) {
        if (channel !in RecordSheet.CHANNELS) return
        _sheet.value = _sheet.value?.copy(channel = channel)
    }

    /**
     * Type the transaction reference.
     *
     * @param reference The reference
     */
    fun typeRecordReference(reference: String) {
        _sheet.value = _sheet.value?.copy(reference = reference.take(RecordSheet.REFERENCE_MAX))
    }

    /**
     * Type a note.
     *
     * @param note The note
     */
    fun typeRecordNote(note: String) {
        _sheet.value = _sheet.value?.copy(note = note.take(RecordSheet.NOTE_MAX))
    }

    /**
     * Say whether a shortfall stays owed on the fee or is waived.
     *
     * @param disposition `carried` or `waived`
     */
    fun chooseRecordDisposition(disposition: String) {
        _sheet.value = _sheet.value?.copy(disposition = disposition)
    }

    /** Close the sheet without recording. */
    fun dismissRecord() {
        _sheet.value = null
    }

    /** Send the record, then read the fee as the server now has it. */
    fun confirmRecord() {
        val sheet = _sheet.value ?: return
        val seat = recordingFor ?: return
        val body = sheet.body() ?: return
        _sheet.value = sheet.copy(busy = true, errorKey = null)
        viewModelScope.launch {
            when (val result = recorder.recordPayment(seat, body)) {
                is AuthResult.Ok -> {
                    _sheet.value = null
                    _recorded.value = true
                    feeId?.let { _state.value = read(it) }
                }
                is AuthResult.Refused ->
                    _sheet.value = _sheet.value?.copy(busy = false, errorKey = result.envelope.error.messageKey)
                AuthResult.TransportFailure -> _sheet.value = _sheet.value?.copy(busy = false, errorKey = OFFLINE_KEY)
            }
        }
    }

    private suspend fun read(extraFeeId: String): ExtraFeeDetailUiState =
        when (val result = repository.fee(extraFeeId)) {
            is AuthResult.Ok -> ExtraFeeDetailUiState.Loaded(result.value)
            is AuthResult.Refused ->
                ExtraFeeDetailUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> ExtraFeeDetailUiState.Failed(OFFLINE_KEY, retryable = true)
        }
}
