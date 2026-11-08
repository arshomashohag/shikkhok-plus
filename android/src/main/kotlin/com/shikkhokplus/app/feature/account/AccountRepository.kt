package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * What the signed-in account screens need from the network: the
 * password, and adding a phone or an email the account lacks.
 *
 * Declared in the feature, as every repository here is, so the feature
 * states what it needs and the network layer supplies it.
 */
interface AccountRepository {
    /**
     * Set a first password, or change the current one.
     *
     * **Every session ends, this one included**, and the server answers
     * with a new pair. The implementation stores it in place of the old
     * one before returning, so the person stays signed in.
     *
     * @param currentPassword The current password when the account has
     *   one; null when it has none
     * @param newPassword The password to set
     * @return The new pair, a refusal, or a transport failure
     */
    suspend fun setPassword(currentPassword: String?, newPassword: String): AuthResult<TokenResponse>

    /**
     * Send a code to a phone or an email to be added to this account.
     *
     * @param identifier The phone or email to add
     * @return The server's acknowledgement, a refusal, or a transport failure
     */
    suspend fun requestContact(identifier: Identifier): AuthResult<IssueResponse>

    /**
     * Present the code, which adds the phone or email.
     *
     * @param identifier The phone or email the code went to
     * @param code The six digits
     * @return The updated account, a refusal, or a transport failure
     */
    suspend fun verifyContact(identifier: Identifier, code: String): AuthResult<MeDto>
}
