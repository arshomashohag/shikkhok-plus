package com.shikkhokplus.app.feature.extrafees

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ExtraFeeDetailDto
import com.shikkhokplus.app.core.network.ExtraFeeSummaryDto

/** The kind of fee, as the server names it. */
enum class FeeKind(val wire: String) {
    /** An exam fee. */
    EXAM("exam"),

    /** Any other fee. */
    OTHER("other"),
    ;

    companion object {
        /**
         * Read the server's value.
         *
         * @param wire The server's `purpose`
         * @return The kind; anything unrecognised reads as other
         */
        fun fromWire(wire: String): FeeKind = if (wire == EXAM.wire) EXAM else OTHER
    }
}

/** What happens to one student when a fee is raised. */
enum class SeatChoice {
    /** Charged the fee's amount. */
    CHARGE,

    /** Charged nothing: listed, and waived. */
    WAIVE,

    /** Not charged and not listed. */
    LEAVE_OUT,
}

/** The batch's list of fees. */
sealed interface ExtraFeesUiState {
    /** Waiting for the list. */
    data object Loading : ExtraFeesUiState

    /**
     * The fees, newest first; empty is the empty state.
     *
     * @property fees The server's summaries
     */
    data class Loaded(val fees: List<ExtraFeeSummaryDto>) : ExtraFeesUiState

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : ExtraFeesUiState
}

/**
 * A student the raise form lists.
 *
 * @property enrollmentId The seat
 * @property name The name the teacher typed
 */
data class RaiseStudent(val enrollmentId: String, val name: String)

/**
 * An exam the fee could be for.
 *
 * @property examId The exam
 * @property title Its title
 */
data class RaiseExam(val examId: String, val title: String)

/**
 * The raise-a-fee form.
 *
 * @property loading Whether the students are still being read
 * @property loadFailedKey Why the students could not be read, or null
 * @property students Who the fee could charge, as the server listed them
 * @property exams The batch's exams, for an exam fee; empty hides the choice
 * @property kind Exam or other
 * @property label The name families see
 * @property examId The linked exam, or null
 * @property typedAmount The amount per student, as typed
 * @property dueOn When it is due, `yyyy-MM-dd`
 * @property choices Students not simply charged; absent means charge
 * @property saving Whether a raise is in flight
 * @property raised The raised fee, once the server stored it
 * @property failureKey Message key for the last refusal, or null
 */
data class RaiseFeeUiState(
    val loading: Boolean = true,
    val loadFailedKey: String? = null,
    val students: List<RaiseStudent> = emptyList(),
    val exams: List<RaiseExam> = emptyList(),
    val kind: FeeKind = FeeKind.EXAM,
    val label: String = "",
    val examId: String? = null,
    val typedAmount: String = "",
    val dueOn: String,
    val choices: Map<String, SeatChoice> = emptyMap(),
    val saving: Boolean = false,
    val raised: ExtraFeeSummaryDto? = null,
    val failureKey: String? = null,
) {
    /**
     * A student's choice.
     *
     * @param enrollmentId The seat
     * @return What happens to them
     */
    fun choiceOf(enrollmentId: String): SeatChoice = choices[enrollmentId] ?: SeatChoice.CHARGE

    /** How many students the fee reaches: everyone not left out. */
    val chargedCount: Int
        get() = students.count { choiceOf(it.enrollmentId) != SeatChoice.LEAVE_OUT }

    /**
     * Whether the form can be sent: format only. The server re-checks
     * every field and refuses what it cannot raise.
     */
    val canRaise: Boolean
        get() =
            !loading && !saving && raised == null && label.isNotBlank() &&
                Money.fromTyped(typedAmount) != null && chargedCount > 0
}

/** One fee's page. */
sealed interface ExtraFeeDetailUiState {
    /** Waiting for the fee. */
    data object Loading : ExtraFeeDetailUiState

    /**
     * The fee and its students.
     *
     * @property fee The server's fee
     */
    data class Loaded(val fee: ExtraFeeDetailDto) : ExtraFeeDetailUiState

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : ExtraFeeDetailUiState
}
