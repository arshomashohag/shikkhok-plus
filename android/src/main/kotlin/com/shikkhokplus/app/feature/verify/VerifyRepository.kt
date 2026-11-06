package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.network.PaymentApprovalBodyDto
import com.shikkhokplus.app.core.network.PaymentReviewDto
import com.shikkhokplus.app.core.network.VerificationQueueDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the payment queue needs from the server (R1). */
interface VerifyRepository {
    /**
     * Read the payments waiting for this teacher and the last day's decisions.
     *
     * @return The queue, a refusal, or a transport failure
     */
    suspend fun queue(): AuthResult<VerificationQueueDto>
}

/** What reviewing one payment needs from the server (R2 to R4). */
interface PaymentReviewRepository {
    /**
     * Read one payment, optionally measured against another purpose.
     *
     * A preview writes nothing: the server answers with the payment as
     * it would read if applied to [purpose], so the comparison and the
     * difference stay the server's.
     *
     * @param submissionId The payment
     * @param purpose `monthly` or `extra` to preview, or null for as stored
     * @param extraFeeId The fee to preview against, with `extra`
     * @return The payment, a refusal, or a transport failure
     */
    suspend fun detail(
        submissionId: String,
        purpose: String? = null,
        extraFeeId: String? = null,
    ): AuthResult<PaymentReviewDto>

    /**
     * Approve a payment with what was received.
     *
     * @param submissionId The payment
     * @param body The amount and how to split it
     * @return The decided payment, or why the server refused
     */
    suspend fun approve(submissionId: String, body: PaymentApprovalBodyDto): AuthResult<PaymentReviewDto>

    /**
     * Reject a payment, recording nothing as received.
     *
     * @param submissionId The payment
     * @param note Why, or null when the teacher gave none
     * @param correcting True when revising a decided payment
     * @return The decided payment, or why the server refused
     */
    suspend fun reject(submissionId: String, note: String?, correcting: Boolean): AuthResult<PaymentReviewDto>
}
