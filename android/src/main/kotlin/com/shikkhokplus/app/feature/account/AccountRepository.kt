package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.core.network.UsernameAvailabilityDto
import com.shikkhokplus.app.core.network.UsernameChangeDto
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

    /**
     * Ask the authenticated lookup whether a username could be taken.
     *
     * Authenticated so a name this account released and may reclaim reads
     * available here (ADR-012), and nowhere else.
     *
     * @param username The candidate, trimmed
     * @return The server's answer, a refusal, or a transport failure
     */
    suspend fun checkUsername(username: String): AuthResult<UsernameAvailabilityDto>

    /**
     * Choose the first username, or rename [FR5.4, FR7.1].
     *
     * Ends no session and returns no tokens: nothing is written to the
     * token store [FR7.5].
     *
     * @param username The candidate, trimmed
     * @param password The password for a rename; null for the first choice
     * @return The stored username and when it may next change, a
     *   refusal, or a transport failure
     */
    suspend fun changeUsername(username: String, password: String?): AuthResult<UsernameChangeDto>

    /**
     * Ask for a code to replace this account's phone or email [FR8.2].
     *
     * @param identifier The new phone or email
     * @param password The account's password
     * @return The server's acknowledgement, a refusal, or a transport failure
     */
    suspend fun replaceContact(identifier: Identifier, password: String): AuthResult<IssueResponse>

    /**
     * Remove this account's phone or email [FR8.4].
     *
     * @param kind Which one
     * @param password The account's password
     * @return The account as it now is, a refusal, or a transport failure
     */
    suspend fun removeContact(kind: IdentifierKind, password: String): AuthResult<MeDto>
}
