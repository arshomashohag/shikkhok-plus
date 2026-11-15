package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.core.network.VerifyResponse
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * The ViewModel state machine: loading, success, error, and the
 * **explicit retry path for a failed write** [TC-8, D-9].
 *
 * These are test-AFTER, which is `team.md`'s stated exception for this
 * surface: with no declared Android experience, a test written before
 * the implementation is as likely to encode a misunderstanding of the
 * framework as to catch a defect — and when it passes, it certifies
 * that misunderstanding.
 *
 * They target the mapping function rather than an untargeted "the
 * ViewModel", which is where every decision the screen depends on
 * actually lives.
 */
class AuthStateMapperTest {

    @Test
    fun `a successful issue moves to awaiting code`() {
        val state = AuthStateMapper.afterIssue(IssueResponse(status = "requested"))
        assertIs<AuthUiState.AwaitingCode>(state)
    }

    @Test
    fun `an issue for an unknown number is indistinguishable`() {
        // The server's response is identical either way [BR2.7]. A
        // client that branched here would rebuild the oracle the
        // server went to some trouble to close.
        val known = AuthStateMapper.afterIssue(IssueResponse(status = "requested"))
        val unknown = AuthStateMapper.afterIssue(IssueResponse(status = "requested"))
        assertEquals(known, unknown)
    }

    @Test
    fun `a successful verify moves to signed in`() {
        val state = AuthStateMapper.afterVerify(
            TokenResponse(
                accessToken = "a.b.c",
                refreshToken = "opaque",
                expiresIn = 900,
            ),
        )
        assertIs<AuthUiState.SignedIn>(state)
    }

    @Test
    fun `a renewed session at a cold start is signed in`() {
        assertEquals(AuthUiState.SignedIn, AuthStateMapper.afterResume(SessionResume.RENEWED))
    }

    @Test
    fun `a session that could not be verified stays signed in`() {
        // No answer -- offline, or a server that failed to answer --
        // says nothing about the credential [FE-1]. Sending the teacher
        // to the OTP screen for it stranded the offline queue.
        assertEquals(AuthUiState.SignedIn, AuthStateMapper.afterResume(SessionResume.UNVERIFIED))
    }

    @Test
    fun `only an ended session goes to sign-in`() {
        assertEquals(AuthUiState.Idle, AuthStateMapper.afterResume(SessionResume.ENDED))
    }

    @Test
    fun `a server error carries the key and the retryable flag`() {
        val state = AuthStateMapper.afterError(
            ErrorEnvelope(
                ErrorBody(
                    code = "TEMPORARILY_UNAVAILABLE",
                    retryable = false,
                    messageKey = "auth.otp.temporarily_unavailable",
                ),
            ),
        )
        val failed = assertIs<AuthUiState.Failed>(state)
        assertEquals("auth.otp.temporarily_unavailable", failed.messageKey)
        assertFalse(failed.retryable)
    }

    @Test
    fun `retryable is READ from the envelope and never inferred`() {
        // The client is forbidden business logic [TC-9], so it does not
        // decide retryability from a status code -- it is told. Two
        // envelopes differing ONLY in the flag must produce states
        // differing only in the flag.
        fun envelope(retryable: Boolean) = ErrorEnvelope(
            ErrorBody("SAME_CODE", retryable, "auth.otp.not_valid"),
        )

        val yes = assertIs<AuthUiState.Failed>(
            AuthStateMapper.afterError(envelope(true)),
        )
        val no = assertIs<AuthUiState.Failed>(
            AuthStateMapper.afterError(envelope(false)),
        )
        assertTrue(yes.retryable)
        assertFalse(no.retryable)
        assertEquals(yes.messageKey, no.messageKey)
    }

    @Test
    fun `a transport failure offers an explicit retry`() {
        // THE RETRY PATH. V1 accepts no write without connectivity and
        // has no local queue, so a failed write must surface an
        // explicit retry rather than queueing silently [TC-8, D-9].
        val failed = assertIs<AuthUiState.Failed>(
            AuthStateMapper.afterTransportFailure(),
        )
        assertTrue(failed.retryable, "a transport failure must be retryable")
        assertEquals(AuthStateMapper.OFFLINE_KEY, failed.messageKey)
    }

    @Test
    fun `a malformed issue response fails rather than proceeding`() {
        val failed = assertIs<AuthUiState.Failed>(
            AuthStateMapper.afterIssue(IssueResponse(status = "")),
        )
        assertTrue(failed.retryable)
    }

    @Test
    fun `a token response missing a token is not a sign in`() {
        val failed = assertIs<AuthUiState.Failed>(
            AuthStateMapper.afterVerify(
                TokenResponse(accessToken = "", refreshToken = "x", expiresIn = 900),
            ),
        )
        assertFalse(failed.retryable)
    }

    // --- U3 [FR2.2, FR4.1, NFR1.1, NFR1.4] -------------------------------------

    private fun envelope(key: String, retryable: Boolean = false, details: Map<String, String>? = null) =
        ErrorEnvelope(ErrorBody(code = "X", retryable = retryable, messageKey = key, details = details))

    @Test
    fun `a one-field sign-in maps a wrong password exactly as before`() {
        assertEquals(
            AuthUiState.Failed("auth.password.wrong", retryable = false, offerCodeFlow = true),
            AuthStateMapper.afterSignIn(AuthResult.Refused(envelope("auth.password.wrong"))),
        )
    }

    @Test
    fun `an unavailable username at verify opens the replacement naming the typed name`() {
        // `previous` is the person's own typed value, never from the
        // response, which carries nothing but the key [NFR1.4].
        assertEquals(
            AuthUiState.ReplaceUsername(previous = "nadia_k"),
            ReplacementStateMapper.afterVerifyRefused(envelope("account.username.unavailable"), "nadia_k"),
        )
    }

    @Test
    fun `any other verify refusal stays on the code step with its tries left`() {
        assertEquals(
            AuthUiState.CodeRejected("auth.otp.wrong", retryable = false, attemptsLeft = "2"),
            ReplacementStateMapper.afterVerifyRefused(
                envelope("auth.otp.wrong", details = mapOf("attempts_left" to "2")),
                "nadia_k",
            ),
        )
    }

    @Test
    fun `a replacement refused for its name or the lookup ceiling stays on the replacement`() {
        listOf("account.username.unavailable", "account.username.bad_dot", "auth.lookup.too_many").forEach { key ->
            assertEquals(
                AuthUiState.ReplaceUsername("nadia_k", messageKey = key),
                ReplacementStateMapper.afterReplacement(AuthResult.Refused(envelope(key)), "nadia_k"),
            )
        }
    }

    @Test
    fun `a spent or expired code on the replacement goes back to the code step`() {
        listOf("auth.otp.expired", "auth.otp.no_tries_left", "auth.otp.not_valid").forEach { key ->
            assertEquals(
                AuthUiState.CodeRejected(key, retryable = false),
                ReplacementStateMapper.afterReplacement(AuthResult.Refused(envelope(key)), "nadia_k"),
            )
        }
    }

    @Test
    fun `a wrong code on the replacement is the ordinary wrong code`() {
        assertEquals(
            AuthUiState.CodeRejected("auth.otp.wrong", retryable = false, attemptsLeft = "1"),
            ReplacementStateMapper.afterReplacement(
                AuthResult.Refused(envelope("auth.otp.wrong", details = mapOf("attempts_left" to "1"))),
                "nadia_k",
            ),
        )
    }

    @Test
    fun `no answer to a replacement is retryable on the replacement`() {
        assertEquals(
            AuthUiState.ReplaceUsername("nadia_k", messageKey = AuthStateMapper.OFFLINE_KEY, retryable = true),
            ReplacementStateMapper.afterReplacement(AuthResult.TransportFailure, "nadia_k"),
        )
    }

    @Test
    fun `an accepted replacement continues to choosing a password`() {
        assertEquals(
            AuthUiState.ChoosePassword(),
            ReplacementStateMapper.afterReplacement(
                AuthResult.Ok(VerifyResponse(passwordSetupToken = "setup", passwordSetupExpiresIn = 600)),
                "nadia_k",
            ),
        )
    }

    @Test
    fun `the mapper never produces English text of its own`() {
        // Every failure names a KEY. A literal sentence here would be
        // unlocalizable and would appear in English in a Bangla UI.
        val states = listOf(
            AuthStateMapper.afterTransportFailure(),
            AuthStateMapper.afterIssue(IssueResponse(status = "")),
        )
        states.filterIsInstance<AuthUiState.Failed>().forEach {
            assertFalse(it.messageKey.contains(" "), "a key, not a sentence")
        }
    }
}
