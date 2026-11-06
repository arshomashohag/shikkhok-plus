package com.shikkhokplus.app.feature.staff

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.core.network.StaffBodyDto
import com.shikkhokplus.app.core.network.StaffDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The message key for a request that never got an answer. */
internal const val OFFLINE_KEY: String = "error.network.unreachable"

/** The longest name, email or role the server stores. */
internal const val STAFF_TEXT_MAX: Int = 120

/** How a staff member is paid, as the server names it. */
enum class PayBasis(val wire: String) {
    /** A salary each month. */
    MONTHLY("monthly"),

    /** A rate per class held. */
    PER_CLASS("per_class"),

    /** Not paid by the centre. */
    NONE("none"),
    ;

    companion object {
        /**
         * Read the server's value.
         *
         * @param wire The server's `pay_basis`
         * @return The basis; anything unrecognised reads as not paid
         */
        fun fromWire(wire: String): PayBasis = entries.firstOrNull { it.wire == wire } ?: NONE
    }
}

/** The console's list. */
sealed interface StaffListUiState {
    /** Waiting for the list. */
    data object Loading : StaffListUiState

    /**
     * The records, teachers and staff together as the server ordered them.
     *
     * @property staff The records
     * @property notice A confirmation to show, such as who was marked as left
     * @property failureKey Message key for a refused leave, or null
     */
    data class Loaded(
        val staff: List<StaffDto>,
        val notice: String? = null,
        val failureKey: String? = null,
    ) : StaffListUiState

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : StaffListUiState
}

/**
 * Holds the console's list and marking someone as left.
 *
 * @property repository The network
 */
class StaffListViewModel(
    private val repository: StaffRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<StaffListUiState>(StaffListUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<StaffListUiState> = _state.asStateFlow()

    private var records: List<StaffDto> = emptyList()

    /** Read the list. */
    fun load() {
        viewModelScope.launch { _state.value = read() }
    }

    /** Read again after a failure. */
    fun retry() {
        _state.value = StaffListUiState.Loading
        load()
    }

    /**
     * Find a loaded record, for the editor to start from.
     *
     * @param staffId The record
     * @return The record, or null when it is not in the last read
     */
    fun recordFor(staffId: String): StaffDto? = records.firstOrNull { it.staffId == staffId }

    /**
     * Mark someone as left today, then read the list again.
     *
     * @param staffId The record
     */
    fun leave(staffId: String) {
        viewModelScope.launch {
            when (val result = repository.leave(staffId, leftOn = null)) {
                is AuthResult.Ok -> {
                    val next = read()
                    _state.value =
                        (next as? StaffListUiState.Loaded)?.copy(notice = result.value.displayName) ?: next
                }
                is AuthResult.Refused -> keepWithFailure(result.envelope.error.messageKey)
                AuthResult.TransportFailure -> keepWithFailure(OFFLINE_KEY)
            }
        }
    }

    private fun keepWithFailure(key: String) {
        val current = _state.value as? StaffListUiState.Loaded ?: return
        _state.value = current.copy(failureKey = key, notice = null)
    }

    private suspend fun read(): StaffListUiState =
        when (val result = repository.list()) {
            is AuthResult.Ok -> {
                records = result.value
                StaffListUiState.Loaded(result.value)
            }
            is AuthResult.Refused ->
                StaffListUiState.Failed(result.envelope.error.messageKey, result.envelope.error.retryable)
            AuthResult.TransportFailure -> StaffListUiState.Failed(OFFLINE_KEY, retryable = true)
        }
}

/** What the staff form is doing. */
sealed interface StaffFormMode {
    /** Inviting a teacher, who gets app access once they accept. */
    data object InviteTeacher : StaffFormMode

    /** Adding someone who works here without app access. */
    data object AddOther : StaffFormMode

    /**
     * Correcting a record.
     *
     * @property existing The record as last read
     */
    data class Edit(val existing: StaffDto) : StaffFormMode
}

/**
 * The staff form.
 *
 * @property mode What it is doing
 * @property name Their name
 * @property phone Their number; required to invite a teacher
 * @property email Their email
 * @property roleLabel What they do, for other staff
 * @property address Their address, every part optional
 * @property basis How they are paid
 * @property typedRate The rate as typed
 * @property joinedOn When they joined, or blank for today
 * @property saving Whether a save is in flight
 * @property saved The record, once the server stored it
 * @property failureKey Message key for the last refusal, or null
 */
data class StaffFormUiState(
    val mode: StaffFormMode,
    val name: String = "",
    val phone: String = "",
    val email: String = "",
    val roleLabel: String = "",
    val address: PostalAddress = PostalAddress(),
    val basis: PayBasis = PayBasis.MONTHLY,
    val typedRate: String = "",
    val joinedOn: String = "",
    val saving: Boolean = false,
    val saved: StaffDto? = null,
    val failureKey: String? = null,
) {
    /** Whether the form is for other staff, who have a role and no invitation. */
    val isOther: Boolean
        get() = mode is StaffFormMode.AddOther || (mode as? StaffFormMode.Edit)?.existing?.isTeacher == false

    /**
     * Whether the form can be sent: format only. A name; a number to invite
     * a teacher by; an amount that parses with a paid basis.
     */
    val canSave: Boolean
        get() =
            !saving && saved == null && name.isNotBlank() &&
                (mode != StaffFormMode.InviteTeacher || phone.isNotBlank()) &&
                (basis == PayBasis.NONE || Money.fromTyped(typedRate) != null)
}

/**
 * Holds the staff form: inviting a teacher, adding other staff, or
 * correcting a record. The server checks every value.
 *
 * @property repository The network
 * @param mode What the form is doing
 */
class StaffFormViewModel(
    private val repository: StaffRepository,
    mode: StaffFormMode,
) : ViewModel() {

    private val _state = MutableStateFlow(initial(mode))

    /** What the form renders. */
    val state: StateFlow<StaffFormUiState> = _state.asStateFlow()

    /**
     * Edit the name.
     *
     * @param text Their name
     */
    fun name(text: String) = _state.update { it.copy(name = text.take(STAFF_TEXT_MAX), failureKey = null) }

    /**
     * Edit the phone.
     *
     * @param text Their number
     */
    fun phone(text: String) = _state.update { it.copy(phone = text, failureKey = null) }

    /**
     * Edit the email.
     *
     * @param text Their email
     */
    fun email(text: String) = _state.update { it.copy(email = text.take(STAFF_TEXT_MAX), failureKey = null) }

    /**
     * Edit what they do.
     *
     * @param text Their role
     */
    fun roleLabel(text: String) = _state.update { it.copy(roleLabel = text.take(STAFF_TEXT_MAX), failureKey = null) }

    /**
     * Edit the address.
     *
     * @param address The address as it now reads
     */
    fun address(address: PostalAddress) = _state.update { it.copy(address = address, failureKey = null) }

    /**
     * Choose how they are paid; not paid clears the amount.
     *
     * @param basis The basis
     */
    fun basis(basis: PayBasis) =
        _state.update {
            it.copy(basis = basis, typedRate = if (basis == PayBasis.NONE) "" else it.typedRate, failureKey = null)
        }

    /**
     * Type the pay amount.
     *
     * @param text The amount as typed
     */
    fun rate(text: String) = _state.update { it.copy(typedRate = text, failureKey = null) }

    /**
     * Pick the joining date.
     *
     * @param isoDate `yyyy-MM-dd`
     */
    fun joinedOn(isoDate: String) = _state.update { it.copy(joinedOn = isoDate, failureKey = null) }

    /** Send the form, when it can be sent. */
    fun save() {
        val form = _state.value
        if (!form.canSave) return
        val body = bodyOf(form)
        _state.update { it.copy(saving = true, failureKey = null) }
        viewModelScope.launch {
            val result =
                when (val mode = form.mode) {
                    StaffFormMode.InviteTeacher -> repository.inviteTeacher(body)
                    StaffFormMode.AddOther -> repository.addOther(body)
                    is StaffFormMode.Edit -> repository.update(mode.existing.staffId, body)
                }
            when (result) {
                is AuthResult.Ok -> _state.update { it.copy(saving = false, saved = result.value) }
                is AuthResult.Refused ->
                    _state.update { it.copy(saving = false, failureKey = result.envelope.error.messageKey) }
                AuthResult.TransportFailure -> _state.update { it.copy(saving = false, failureKey = OFFLINE_KEY) }
            }
        }
    }

    private companion object {
        fun initial(mode: StaffFormMode): StaffFormUiState {
            val row = (mode as? StaffFormMode.Edit)?.existing ?: return StaffFormUiState(mode)
            return StaffFormUiState(
                mode = mode,
                name = row.displayName,
                phone = row.phone.orEmpty(),
                email = row.email.orEmpty(),
                roleLabel = row.roleLabel.orEmpty(),
                address =
                    PostalAddress(
                        house = row.staffHouse.orEmpty(),
                        road = row.staffRoad.orEmpty(),
                        city = row.staffCity.orEmpty(),
                        postcode = row.staffPostcode.orEmpty(),
                    ),
                basis = PayBasis.fromWire(row.payBasis),
                typedRate = row.payRate?.toString().orEmpty(),
                joinedOn = row.joinedOn,
            )
        }

        fun bodyOf(form: StaffFormUiState): StaffBodyDto {
            fun orNull(text: String) = text.trim().ifEmpty { null }
            return StaffBodyDto(
                displayName = form.name.trim(),
                phone = orNull(form.phone).takeIf { form.mode !is StaffFormMode.Edit },
                email = orNull(form.email),
                roleLabel = orNull(form.roleLabel).takeIf { form.isOther },
                staffHouse = orNull(form.address.house),
                staffRoad = orNull(form.address.road),
                staffCity = orNull(form.address.city),
                staffPostcode = orNull(form.address.latinPostcode),
                payBasis = form.basis.wire,
                payRate = Money.fromTyped(form.typedRate).takeIf { form.basis != PayBasis.NONE },
                joinedOn = form.joinedOn.ifBlank { null },
            )
        }
    }
}
