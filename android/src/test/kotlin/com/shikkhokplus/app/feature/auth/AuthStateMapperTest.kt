package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse
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
