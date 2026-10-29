package com.shikkhokplus.app.feature.guardian

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.pay.PayOption
import com.shikkhokplus.app.feature.student.NextClass

/**
 * The most urgent fee for a child, as the server chose it.
 *
 * @property option The month to pay, with its amount and due date
 * @property totalDue Everything that batch owes
 * @property laterPeriods How many later months also owe
 * @property daysLate Days late, or null when not yet late
 */
data class GuardianPayment(
    val option: PayOption,
    val totalDue: Money,
    val laterPeriods: Int,
    val daysLate: Int?,
)

/**
 * A payment sent and being checked.
 *
 * @property batchName The batch
 * @property period The month
 * @property amount What was sent, if known
 * @property channel Which app
 * @property sentAt When it was sent, if known
 */
data class WaitingCard(
    val batchName: String,
    val period: String,
    val amount: Money?,
    val channel: String,
    val sentAt: String?,
)

/** How a result compares with the one before, as the server said. */
enum class Trend {
    /** Better than the last test, as a share of its total. */
    UP,

    /** Worse. */
    DOWN,

    /** The same. */
    SAME,

    /** The batch's first test. */
    FIRST,
}

/**
 * A child's latest result in one batch.
 *
 * @property enrollmentId The seat, which opens G2
 * @property batchName The batch
 * @property title The exam
 * @property date `yyyy-MM-dd`
 * @property marks The mark
 * @property totalMarks Out of how many
 * @property previousMarks The mark before it, or null
 * @property trend How it compares
 */
data class ResultCard(
    val enrollmentId: String,
    val batchName: String,
    val title: String,
    val date: String,
    val marks: Int,
    val totalMarks: Int,
    val previousMarks: Int?,
    val trend: Trend,
)

/**
 * One of a child's batches.
 *
 * @property enrollmentId The seat
 * @property batchName The batch
 * @property teacherName The teacher, or null
 * @property next The next class, or null
 */
data class ChildBatch(
    val enrollmentId: String,
    val batchName: String,
    val teacherName: String?,
    val next: NextClass?,
)

/**
 * One child, as G1 shows them.
 *
 * @property key The child's first seat
 * @property name The teacher-typed name
 * @property batchCount How many batches
 * @property payment The most urgent fee, or null
 * @property waiting Payments being checked
 * @property results Each batch's latest result
 * @property batches The batches
 */
data class ChildCard(
    val key: String,
    val name: String,
    val batchCount: Int,
    val payment: GuardianPayment?,
    val waiting: List<WaitingCard>,
    val results: List<ResultCard>,
    val batches: List<ChildBatch>,
)

/**
 * Everything the guardian home renders.
 *
 * **Switching child replaces the shown child** [BR4.2]: one child's
 * figures are never shown under another's name, and Back cannot reach
 * the previous child.
 */
sealed interface GuardianUiState {
    /** Nothing has been asked for yet. */
    data object Idle : GuardianUiState

    /** A request is in flight. */
    data object Loading : GuardianUiState

    /**
     * The guardian's children, one shown.
     *
     * @property children Every child, by name
     * @property selected The shown child's index
     * @property switched Whether the guardian has just switched child,
     *   which the screen says out loud
     */
    data class Loaded(
        val children: List<ChildCard>,
        val selected: Int = 0,
        val switched: Boolean = false,
    ) : GuardianUiState {
        /** The shown child. */
        val child: ChildCard get() = children[selected]
    }

    /**
     * No child linked yet.
     *
     * @property phone The guardian's number, for the teacher, or null
     */
    data class Empty(val phone: String?) : GuardianUiState

    /**
     * Something failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : GuardianUiState
}
