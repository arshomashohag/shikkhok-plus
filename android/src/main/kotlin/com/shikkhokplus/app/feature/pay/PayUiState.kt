package com.shikkhokplus.app.feature.pay

import com.shikkhokplus.app.core.model.Money

/**
 * One month the student can pay for, as the server listed it.
 *
 * @property enrollmentId The seat the claim is posted against
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
 * A batch not offered because its payment is being checked.
 *
 * @property batchName The batch
 * @property period The month being checked
 */
data class WaitingLine(val batchName: String, val period: String)

/**
 * Where to send the money, when the teacher set a number.
 *
 * @property number The collection number
 * @property service Which service it belongs to, if the teacher said
 * @property teacherName Who it goes to, if the teacher named themselves
 */
data class PayDestination(val number: String, val service: String?, val teacherName: String?)

/**
 * What the student has typed. Kept across a failed send.
 *
 * @property channel The app they used, or null until chosen
 * @property transactionId The ID from the SMS
 * @property amount What they sent, as typed
 */
data class PayForm(val channel: String? = null, val transactionId: String = "", val amount: String = "")

/** Why the form will not send yet, as the form can tell. Format only. */
enum class FormProblem {
    /** The transaction ID is too short to be one. */
    TRANSACTION_ID_SHORT,
}

/**
 * The payment as sent, for the "Payment sent" screen.
 *
 * @property amount What was claimed
 * @property channel Which app
 * @property transactionId The ID quoted
 * @property submittedAt When the server recorded it
 */
data class SentPayment(val amount: Money, val channel: String, val transactionId: String?, val submittedAt: String)

/** Everything the S3 screen renders. */
sealed interface PayUiState {
    /** Reading what can be paid. */
    data object Loading : PayUiState

    /**
     * Choosing which fee to pay.
     *
     * @property options The months on offer, in the server's order
     * @property waiting Batches whose payment is being checked
     */
    data class Choosing(val options: List<PayOption>, val waiting: List<WaitingLine>) : PayUiState

    /**
     * Filling in how it was paid.
     *
     * @property option The fee being paid
     * @property destination Where to send it, or null when the teacher set no number
     * @property channels The apps the server accepts
     * @property form What has been typed
     * @property problem A format problem to show beside the ID, or null
     * @property sending Whether it is on its way
     * @property failedKey Why the last send failed, or null
     * @property canChange Whether there are other fees to go back to
     */
    data class Filling(
        val option: PayOption,
        val destination: PayDestination?,
        val channels: List<String>,
        val form: PayForm,
        val problem: FormProblem? = null,
        val sending: Boolean = false,
        val failedKey: String? = null,
        val canChange: Boolean = false,
    ) : PayUiState

    /**
     * Sent; waiting for the teacher.
     *
     * @property option The fee it was for
     * @property payment What was sent
     * @property teacherName Who will check it, if known
     */
    data class Sent(val option: PayOption, val payment: SentPayment, val teacherName: String?) : PayUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : PayUiState
}
