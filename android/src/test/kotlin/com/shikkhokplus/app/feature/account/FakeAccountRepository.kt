package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.core.network.DeletionSummaryDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.core.network.UsernameAvailabilityDto
import com.shikkhokplus.app.core.network.UsernameChangeDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.profile.ProfileRepository

/**
 * A server for the U3 account screens: each answer is queued by the test,
 * and every call is recorded, so a test can assert what was sent and that
 * a password reached the repository exactly once.
 */
internal class FakeAccountRepository : AccountRepository, ProfileRepository {
    val changes = mutableListOf<Pair<String, String?>>()
    val replacements = mutableListOf<Pair<Identifier, String>>()
    val verifications = mutableListOf<Pair<Identifier, String>>()
    val removals = mutableListOf<Pair<IdentifierKind, String>>()
    val lookups = mutableListOf<String>()
    var reads = 0

    val changeAnswers = ArrayDeque<AuthResult<UsernameChangeDto>>()
    val replaceAnswers = ArrayDeque<AuthResult<IssueResponse>>()
    val verifyAnswers = ArrayDeque<AuthResult<MeDto>>()
    val removeAnswers = ArrayDeque<AuthResult<MeDto>>()
    val profileAnswers = ArrayDeque<AuthResult<MeDto>>()

    override suspend fun setPassword(currentPassword: String?, newPassword: String): AuthResult<TokenResponse> =
        AuthResult.TransportFailure

    override suspend fun requestContact(identifier: Identifier): AuthResult<IssueResponse> =
        AuthResult.TransportFailure

    override suspend fun verifyContact(identifier: Identifier, code: String): AuthResult<MeDto> {
        verifications += identifier to code
        return verifyAnswers.removeFirstOrNull() ?: AuthResult.TransportFailure
    }

    override suspend fun checkUsername(username: String): AuthResult<UsernameAvailabilityDto> {
        lookups += username
        return AuthResult.Ok(UsernameAvailabilityDto("available"))
    }

    override suspend fun changeUsername(username: String, password: String?): AuthResult<UsernameChangeDto> {
        changes += username to password
        return changeAnswers.removeFirstOrNull() ?: AuthResult.TransportFailure
    }

    override suspend fun replaceContact(identifier: Identifier, password: String): AuthResult<IssueResponse> {
        replacements += identifier to password
        return replaceAnswers.removeFirstOrNull() ?: AuthResult.TransportFailure
    }

    override suspend fun removeContact(kind: IdentifierKind, password: String): AuthResult<MeDto> {
        removals += kind to password
        return removeAnswers.removeFirstOrNull() ?: AuthResult.TransportFailure
    }

    override suspend fun profile(): AuthResult<MeDto> {
        reads++
        return profileAnswers.removeFirstOrNull() ?: AuthResult.TransportFailure
    }

    override suspend fun save(selfName: String?, address: PostalAddress?): AuthResult<MeDto> =
        AuthResult.TransportFailure

    override suspend fun deleteAccount(): AuthResult<Unit> = AuthResult.TransportFailure

    override suspend fun deletionSummary(): AuthResult<DeletionSummaryDto> = AuthResult.TransportFailure

    companion object {
        /**
         * A refusal envelope.
         *
         * @param key The message key
         * @param retryable The server's flag
         * @param details The details, or null
         * @return The refusal
         */
        fun refused(key: String, retryable: Boolean = false, details: Map<String, String>? = null) =
            AuthResult.Refused(ErrorEnvelope(ErrorBody("X", retryable, key, details)))
    }
}
