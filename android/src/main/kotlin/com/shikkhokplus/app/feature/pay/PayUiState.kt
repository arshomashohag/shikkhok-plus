package com.shikkhokplus.app.feature.pay

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.OwedTogetherDto
import com.shikkhokplus.app.core.network.PaymentMethodDto
import com.shikkhokplus.app.core.network.PaymentSubmitDto
import com.shikkhokplus.app.core.network.PaymentSubmittedDto

/**
 * One month a guardian's home offers to pay, as the server listed it.
 *
 * @property enrollmentId The seat the payment opens on
 * @property batchName The batch
 * @property period The month, `YYYY-MM`
 * @property amountDue What is still owed on it
 * @property dueDate When it was due, `yyyy-MM-dd`, or null
 * @property totalDue Everything the seat owes as the server folded it, or null
 */
data class PayOption(
    val enrollmentId: String,
    val batchName: String,
    val period: String,
    val amountDue: Money,
    val dueDate: String?,
    val totalDue: Money? = null,
)

/**
 * One child's accepted seat in a batch.
 *
 * @property enrollmentId The seat the payment is posted against
 * @property childName The child, or null when the payer is the student
 */
data class PaySeat(val enrollmentId: String, val childName: String?)

/**
 * A batch the payer holds an accepted seat in.
 *
 * @property key Tells two batches apart
 * @property name The batch
 * @property seats The seats the payer may pay for in it, in order
 */
data class PayBatch(val key: String, val name: String, val seats: List<PaySeat>)

/** Where the money went. */
sealed interface PayChoice {
    /**
     * One of the teacher's listed methods.
     *
     * @property method The method as the server listed it
     */
    data class Method(val method: PaymentMethodDto) : PayChoice

    /** Money handed over in person. */
    data object Cash : PayChoice
}

/**
 * The batch, children and methods a payment is being made against.
 *
 * @property batches Every batch on offer, for the picker
 * @property batch The chosen batch
 * @property selected The seats the payment covers
 * @property methods The chosen batch's teacher's methods
 * @property teacherName Who the money goes to, if known
 */
data class PayScope(
    val batches: List<PayBatch>,
    val batch: PayBatch,
    val selected: List<String>,
    val methods: List<PaymentMethodDto>,
    val teacherName: String?,
)

/**
 * What the payer has typed. Kept across a failed send.
 *
 * @property transactionId The mobile reference
 * @property fromAccount The paying bank account
 * @property amount What they sent, as typed
 * @property paidOn The day the money moved, `yyyy-MM-dd`
 * @property note Free text for the teacher
 */
data class PayForm(
    val paidOn: String,
    val transactionId: String = "",
    val fromAccount: String = "",
    val amount: String = "",
    val note: String = "",
)

/** Why the form will not send yet, as the form can tell. Format only. */
enum class FormProblem {
    /** The transaction ID is too short to be one. */
    TRANSACTION_ID_SHORT,
}

/**
 * One payment the payer confirmed, and the replay key it went with.
 *
 * **One key per attempt, not per tap** [PA-DB-1]. On a poor network a
 * send can time out after the server has already recorded it; the payer
 * then taps Send again, and without a key the teacher receives the same
 * payment twice as two pending claims. Sending the identical payment
 * again reuses the key, and the server answers with the submission it
 * already holds. Anything the payer changed makes it a different
 * payment, which gets a fresh key.
 *
 * @property payment What was sent, without its key, so the next send can
 *   be compared against it
 * @property clientMutationId The key, a random UUID: no device
 *   identifier of any kind [TC-3, D-37]
 */
data class PaymentAttempt(
    val payment: PaymentSubmitDto,
    val clientMutationId: String,
) {
    /** The body to send: the payment, carrying this attempt's key. */
    val request: PaymentSubmitDto
        get() = payment.copy(clientMutationId = clientMutationId)
}

/**
 * Where a sent payment's record stands, as the sent page renders it.
 *
 * Read from the server's `status`, never decided here [TC-9]. One per
 * value the response schema allows -- `pending`, `approved`, `rejected`.
 */
enum class SentOutcome {
    /** Recorded, waiting for the teacher to check it. */
    PENDING,

    /** Already approved: a late resend of a payment the teacher accepted. */
    APPROVED,

    /** Already rejected: a late resend of a payment the teacher refused. */
    REJECTED,
}

/** Everything the "Send money" screens render. */
sealed interface PayUiState {
    /** Reading the seats and methods. */
    data object Loading : PayUiState

    /** The payer holds no accepted seat to pay for. */
    data object NoSeats : PayUiState

    /**
     * F2: choosing how to pay.
     *
     * @property scope The batch, children and methods
     */
    data class Methods(val scope: PayScope) : PayUiState

    /**
     * F3 and F4: the form for one way of paying.
     *
     * @property scope The batch, children and methods
     * @property choice Where the money went
     * @property owed The server's owed line for the chosen children, or null
     * @property form What has been typed
     * @property problem A format problem to show, or null
     * @property sending Whether it is on its way
     * @property failedKey Why the last send failed, or null
     * @property attempt The payment last sent from this form and the key
     *   it carried, or null before the first send. Kept after a failure
     *   so that sending the same payment again is a retry of the same
     *   attempt rather than a second payment
     */
    data class Filling(
        val scope: PayScope,
        val choice: PayChoice,
        val owed: OwedTogetherDto?,
        val form: PayForm,
        val problem: FormProblem? = null,
        val sending: Boolean = false,
        val failedKey: String? = null,
        val attempt: PaymentAttempt? = null,
    ) : PayUiState

    /**
     * F5: sent -- usually waiting for the teacher.
     *
     * @property batchName The batch
     * @property teacherName Who will check it, if known
     * @property choice Where the money went
     * @property payment What the server recorded
     * @property reference The transaction ID or paying account quoted, or null
     * @property outcome Where the server's record stands. Not always
     *   pending: a resend of a payment the server already holds is
     *   answered with that ORIGINAL submission, and the teacher may have
     *   decided it in the meantime
     */
    data class Sent(
        val batchName: String,
        val teacherName: String?,
        val choice: PayChoice,
        val payment: PaymentSubmittedDto,
        val reference: String?,
        val outcome: SentOutcome = SentOutcome.PENDING,
    ) : PayUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : PayUiState
}
