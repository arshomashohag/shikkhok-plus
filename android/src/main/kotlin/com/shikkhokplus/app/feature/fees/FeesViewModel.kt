package com.shikkhokplus.app.feature.fees

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.FeeHistoryDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

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
}

/**
 * Holds the fee history screen's state. Holds no business logic
 * [TC-9, D-31].
 *
 * Every decision is delegated to [FeeStateMapper], including the
 * **total**, which the server computes: summing the rows here would
 * be money arithmetic on the client [D-20].
 */
class FeesViewModel(
    private val repository: FeesRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<FeeUiState>(FeeUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<FeeUiState> = _state.asStateFlow()

    private var lastAction: (() -> Unit)? = null

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
        _state.value = FeeUiState.Loading
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
}
