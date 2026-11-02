package com.shikkhokplus.app.feature.pay

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.OwedTogetherDto
import com.shikkhokplus.app.core.network.PaymentMethodDto
import com.shikkhokplus.app.core.network.PaymentSubmittedDto

/**
 * One month a guardian's home offers to pay, as the server listed it.
 *
 * @property enrollmentId The seat the payment opens on
 * @property batchName The batch
 * @property period The month, `YYYY-MM`
 * @property amountDue What is still owed on it
 * @property dueDate When it was due, `yyyy-MM-dd`, or null
 */
data class PayOption(
    val enrollmentId: String,
    val batchName: String,
    val period: String,
    val amountDue: Money,
    val dueDate: String?,
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
     */
    data class Filling(
        val scope: PayScope,
        val choice: PayChoice,
        val owed: OwedTogetherDto?,
        val form: PayForm,
        val problem: FormProblem? = null,
        val sending: Boolean = false,
        val failedKey: String? = null,
    ) : PayUiState

    /**
     * F5: sent, waiting for the teacher.
     *
     * @property batchName The batch
     * @property teacherName Who will check it, if known
     * @property choice Where the money went
     * @property payment What the server recorded
     * @property reference The transaction ID or paying account quoted, or null
     */
    data class Sent(
        val batchName: String,
        val teacherName: String?,
        val choice: PayChoice,
        val payment: PaymentSubmittedDto,
        val reference: String?,
    ) : PayUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : PayUiState
}
