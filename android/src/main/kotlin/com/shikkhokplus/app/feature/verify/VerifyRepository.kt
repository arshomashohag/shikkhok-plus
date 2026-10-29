package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ShortfallPreviewDto
import com.shikkhokplus.app.core.network.VerificationQueueDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the payment-check screen needs from the server (T4). */
interface VerifyRepository {
    /**
     * Read the claims waiting for this teacher and the last day's decisions.
     *
     * @return The queue, a refusal, or a transport failure
     */
    suspend fun queue(): AuthResult<VerificationQueueDto>

    /**
     * Ask what approving an amount would leave short.
     *
     * @param claimId The claim
     * @param approvedAmount The amount being considered
     * @return The shortfall, a refusal, or a transport failure
     */
    suspend fun preview(claimId: String, approvedAmount: Money): AuthResult<ShortfallPreviewDto>

    /**
     * Approve a claim, whole or in part.
     *
     * @param claimId The claim
     * @param approvedAmount What is accepted
     * @param disposition `carried` or `waived` where the server asks
     * @return Nothing on success, or why the server refused
     */
    suspend fun approve(claimId: String, approvedAmount: Money, disposition: String?): AuthResult<Unit>

    /**
     * Reject a claim, recording nothing as received.
     *
     * @param claimId The claim
     * @return Nothing on success, or why the server refused
     */
    suspend fun reject(claimId: String): AuthResult<Unit>
}
