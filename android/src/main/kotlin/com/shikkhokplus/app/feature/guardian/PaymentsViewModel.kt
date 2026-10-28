package com.shikkhokplus.app.feature.guardian

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.PayablesDto
import com.shikkhokplus.app.core.network.PaymentsDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.pay.PayOption
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** What G3 needs from the network. */
interface PaymentsRepository {
    /**
     * Read a child's fee history.
     *
     * @param seat Any one of the child's seats
     * @return The history, or a failure
     */
    suspend fun payments(seat: String): AuthResult<PaymentsDto>

    /**
     * Read what can be paid for the child, for the pay button.
     *
     * @param seat Any one of the child's seats
     * @return The payables, or a failure
     */
    suspend fun payables(seat: String): AuthResult<PayablesDto>
}

/** Where one month's payment stands, as the server named it. */
enum class LineState {
    /** Paid in full. */
    PAID,

    /** Part paid. */
    PARTLY_PAID,

    /** Waived by the teacher. */
    WAIVED,

    /** Sent and being checked. */
    VERIFYING,

    /** Owed. */
    DUE,
}

/**
 * One batch's fee in one month.
 *
 * @property batchName The batch
 * @property amount What the month charged
 * @property state Where its payment stands
 * @property dueDate `yyyy-MM-dd`
 * @property sentOn When the payment was sent, or null
 * @property decidedOn When it was approved, or null
 * @property channel Which app, or null
 */
data class PaymentLine(
    val batchName: String,
    val amount: Money,
    val state: LineState,
    val dueDate: String,
    val sentOn: String?,
    val decidedOn: String?,
    val channel: String?,
)

/**
 * One month.
 *
 * @property period `YYYY-MM`
 * @property lines One per batch
 */
data class PaymentMonth(val period: String, val lines: List<PaymentLine>)

/** Everything G3 renders. */
sealed interface PaymentsUiState {
    /** A request is in flight. */
    data object Loading : PaymentsUiState

    /**
     * The history.
     *
     * @property childName The child
     * @property year The year the total covers
     * @property paidThisYear What was approved this year
     * @property months Newest first
     * @property next The fee the pay button pays, or null
     */
    data class Loaded(
        val childName: String,
        val year: Int,
        val paidThisYear: Money,
        val months: List<PaymentMonth>,
        val next: PayOption?,
    ) : PaymentsUiState

    /**
     * It failed: the screen must not invite paying again blind.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : PaymentsUiState
}

/**
 * Holds G3, a child's payments. Holds no business logic [TC-9].
 *
 * @property repository The network
 */
class PaymentsViewModel(
    private val repository: PaymentsRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<PaymentsUiState>(PaymentsUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<PaymentsUiState> = _state.asStateFlow()

    /**
     * Read the child's history and what can be paid.
     *
     * @param seat Any one of the child's seats
     */
    fun load(seat: String) {
        _state.value = PaymentsUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val history = repository.payments(seat)) {
                    is AuthResult.Ok -> {
                        val next =
                            (repository.payables(seat) as? AuthResult.Ok)?.value?.payable?.firstOrNull()
                        PaymentsMapper.afterLoad(history.value, next?.let(GuardianStateMapper::option))
                    }
                    is AuthResult.Refused ->
                        PaymentsUiState.Failed(history.envelope.error.messageKey, history.envelope.error.retryable)
                    AuthResult.TransportFailure -> PaymentsUiState.Failed(GuardianStateMapper.OFFLINE_KEY, true)
                }
        }
    }
}

/** Maps G3's response. Pure. */
object PaymentsMapper {
    /**
     * Map a loaded history.
     *
     * @param dto The server's history
     * @param next The fee to offer, or null
     * @return The state to render
     */
    fun afterLoad(dto: PaymentsDto, next: PayOption?): PaymentsUiState {
        val months =
            dto.months.map { month ->
                PaymentMonth(
                    month.period,
                    month.lines.map {
                        val state = stateOf(it.state) ?: return PaymentsUiState.Failed(UNEXPECTED_KEY, false)
                        PaymentLine(it.batchName, it.amount, state, it.dueDate, it.sentOn, it.decidedOn, it.channel)
                    },
                )
            }
        return PaymentsUiState.Loaded(dto.displayName, dto.year, dto.paidThisYear, months, next)
    }

    /**
     * Name a server line state.
     *
     * An unknown state fails the screen rather than reading as owed: a
     * paid month shown as due is how a guardian pays twice.
     *
     * @param state The wire value
     * @return The state, or null when unknown
     */
    private fun stateOf(state: String): LineState? =
        when (state) {
            "paid" -> LineState.PAID
            "partly_paid" -> LineState.PARTLY_PAID
            "waived" -> LineState.WAIVED
            "verifying" -> LineState.VERIFYING
            "due" -> LineState.DUE
            else -> null
        }

    /** The key shown for a response this version cannot read. */
    private const val UNEXPECTED_KEY: String = "error.unexpected"
}
