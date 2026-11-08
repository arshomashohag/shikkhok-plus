package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.model.emailIsWellFormed
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.PasswordSetupRequest
import com.shikkhokplus.app.core.network.PasswordSignInRequest
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.core.network.VerifyResponse
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The password half of sign-in, as the mapper decides it: what a
 * sign-in, a verified code and a password setup each lead to, and the
 * client's own length-and-match check.
 *
 * Test-first by `team.md`'s predicate for the parts that grant a
 * session -- a wrong answer there is an authorization error -- and the
 * expected values are knowable from the contract without the code.
 */
class PasswordFlowMapperTest {

    private fun refused(key: String, retryable: Boolean = false) =
        AuthResult.Refused(ErrorEnvelope(ErrorBody(code = "X", retryable = retryable, messageKey = key)))

    // --- Sign-in ----------------------------------------------------------------

    @Test
    fun `a sign-in answered with a pair is signed in`() {
        assertEquals(
            AuthUiState.SignedIn,
            AuthStateMapper.afterSignIn(AuthResult.Ok(VerifyResponse("a.b.c", "r1", 900))),
        )
    }

    @Test
    fun `a sign-in answered with a challenge goes to the second step`() {
        assertEquals(
            AuthUiState.SecondStep(),
            AuthStateMapper.afterSignIn(AuthResult.Ok(VerifyResponse(mfaRequired = true, mfaChallenge = "chal"))),
        )
    }

    @Test
    fun `a wrong password offers the code flow, because it may be a first password`() {
        // The server gives ONE answer for an unknown account, an account
        // with no password yet, and a wrong password. The code flow is the
        // way on for the second, so the hint goes with every one.
        assertEquals(
            AuthUiState.Failed("auth.password.wrong", retryable = false, offerCodeFlow = true),
            AuthStateMapper.afterSignIn(refused("auth.password.wrong")),
        )
    }

    @Test
    fun `too many attempts also offers the code flow`() {
        val state = AuthStateMapper.afterSignIn(refused("auth.password.too_many_attempts")) as AuthUiState.Failed

        assertTrue(state.offerCodeFlow)
    }

    @Test
    fun `the network-wide ceiling does not offer the code flow, which would hit it too`() {
        val state = AuthStateMapper.afterSignIn(refused("auth.verify.temporarily_unavailable")) as AuthUiState.Failed

        assertFalse(state.offerCodeFlow)
        assertEquals(AuthStep.SIGN_IN, state.step)
    }

    @Test
    fun `a sign-in with no answer is retryable and offers no hint`() {
        assertEquals(
            AuthUiState.Failed(AuthStateMapper.OFFLINE_KEY, retryable = true),
            AuthStateMapper.afterSignIn(AuthResult.TransportFailure),
        )
    }

    @Test
    fun `retryability is read from the envelope`() {
        val state = AuthStateMapper.afterSignIn(refused("error.temporarily_unavailable", retryable = true))

        assertEquals(true, (state as AuthUiState.Failed).retryable)
    }

    // --- A verified code ----------------------------------------------------

    @Test
    fun `a verified code asks for a password`() {
        assertEquals(
            AuthUiState.ChoosePassword(mfaRequired = false),
            PasswordStateMapper.afterCodeVerified(VerifyResponse(passwordSetupToken = "setup")),
        )
    }

    @Test
    fun `a verified code for an account with two-step verification asks for its code too`() {
        assertEquals(
            AuthUiState.ChoosePassword(mfaRequired = true),
            PasswordStateMapper.afterCodeVerified(VerifyResponse(mfaRequired = true, passwordSetupToken = "setup")),
        )
    }

    @Test
    fun `a verified code with no setup token is a failure, even with a pair`() {
        // A server from before passwords would send a pair here. Signing
        // in on it would leave an account with no password and no prompt
        // on this path, so it is a failure the client cannot act on.
        assertEquals(
            AuthUiState.Failed(AuthStateMapper.UNEXPECTED_KEY, retryable = false, step = AuthStep.CODE_REQUEST),
            PasswordStateMapper.afterCodeVerified(VerifyResponse("a.b.c", "r1", 900)),
        )
    }

    // --- Choosing a password ----------------------------------------------------

    private val form = AuthUiState.ChoosePassword(mfaRequired = true, useRecovery = true, checking = true)

    @Test
    fun `a set password signs in`() {
        assertEquals(
            AuthUiState.SignedIn,
            PasswordStateMapper.afterPasswordSetup(AuthResult.Ok(TokenResponse("a.b.c", "r1", 900)), form),
        )
    }

    @Test
    fun `an empty pair is a failure rather than a session`() {
        assertEquals(
            AuthUiState.Failed(AuthStateMapper.UNEXPECTED_KEY, retryable = false),
            PasswordStateMapper.afterPasswordSetup(AuthResult.Ok(TokenResponse("", "r1", 900)), form),
        )
    }

    @Test
    fun `a lapsed setup token leaves the form for the code flow's start, not retryable`() {
        assertEquals(
            AuthUiState.Failed("auth.password.setup_expired", retryable = false, step = AuthStep.CODE_REQUEST),
            PasswordStateMapper.afterPasswordSetup(refused("auth.password.setup_expired", retryable = true), form),
        )
    }

    @Test
    fun `any other refusal stays on the form, keeping which code was asked for`() {
        assertEquals(
            AuthUiState.ChoosePassword(mfaRequired = true, useRecovery = true, messageKey = "mfa.locked"),
            PasswordStateMapper.afterPasswordSetup(refused("mfa.locked"), form),
        )
    }

    @Test
    fun `no answer stays on the form with a retry`() {
        assertEquals(
            AuthUiState.ChoosePassword(
                mfaRequired = true,
                useRecovery = true,
                messageKey = AuthStateMapper.OFFLINE_KEY,
                retryable = true,
            ),
            PasswordStateMapper.afterPasswordSetup(AuthResult.TransportFailure, form),
        )
    }

    // --- The client's own check ---------------------------------------------

    @Test
    fun `length is checked at both ends of 8 to 128`() {
        assertEquals(PasswordRules.TOO_SHORT_KEY, PasswordRules.check("a".repeat(7), null))
        assertNull(PasswordRules.check("a".repeat(8), null))
        assertNull(PasswordRules.check("a".repeat(128), null))
        assertEquals(PasswordRules.TOO_LONG_KEY, PasswordRules.check("a".repeat(129), null))
    }

    @Test
    fun `length is counted in code points, as the server counts it`() {
        // Eight emoji are sixteen UTF-16 units: long enough by code
        // points, which is what the server counts.
        val eight = "😀".repeat(8)
        assertEquals(16, eight.length)
        assertNull(PasswordRules.check(eight, null))
        assertEquals(PasswordRules.TOO_SHORT_KEY, PasswordRules.check("😀".repeat(7), null))
    }

    @Test
    fun `a mismatch is caught only once the length is right`() {
        assertEquals(PasswordRules.TOO_SHORT_KEY, PasswordRules.check("short", "other"))
        assertEquals(PasswordRules.MISMATCH_KEY, PasswordRules.check("correct horse", "correct horsE"))
        assertNull(PasswordRules.check("correct horse", "correct horse"))
    }

    @Test
    fun `no composition rule is applied on the client`() {
        // Policy is the server's [team: Layer boundaries]: a password of
        // one repeated letter is the server's to refuse, not this one's.
        assertNull(PasswordRules.check("aaaaaaaa", "aaaaaaaa"))
    }

    @Test
    fun `the client check keeps the rest of the form`() {
        val form = AuthUiState.ChoosePassword(mfaRequired = true, useRecovery = true)

        assertEquals(
            form.copy(messageKey = PasswordRules.MISMATCH_KEY),
            PasswordStateMapper.checkChosen(form, "correct horse", "different one"),
        )
        assertNull(PasswordStateMapper.checkChosen(form, "correct horse", "correct horse"))
    }

    // --- The wire ---------------------------------------------------------------

    @Test
    fun `a password never appears in a request's printed form`() {
        val signIn = PasswordSignInRequest(phone = "+8801711111111", password = "correct horse").toString()
        val setup = PasswordSetupRequest(token = "setup-token", password = "correct horse").toString()

        assertFalse("correct horse" in signIn)
        assertFalse("correct horse" in setup)
        assertFalse("setup-token" in setup)
    }

    @Test
    fun `a sign-in body carries exactly one identifier`() {
        val body =
            ApiClient.json.encodeToString(
                PasswordSignInRequest.serializer(),
                PasswordSignInRequest(email = "rafi@example.com", password = "correct horse"),
            )

        assertEquals("""{"email":"rafi@example.com","password":"correct horse"}""", body)
    }

    @Test
    fun `a verify reply with a setup token decodes, as does one from a password sign-in`() {
        val verified =
            ApiClient.json.decodeFromString(
                VerifyResponse.serializer(),
                """{"access_token":null,"refresh_token":null,"expires_in":null,"mfa_required":false,
                   "mfa_challenge":null,"mfa_expires_in":null,
                   "password_setup_token":"opaque","password_setup_expires_in":600}""",
            )
        assertEquals("opaque", verified.passwordSetupToken)
        assertEquals(600, verified.passwordSetupExpiresIn)

        val signedIn =
            ApiClient.json.decodeFromString(
                VerifyResponse.serializer(),
                """{"access_token":"a","refresh_token":"r","expires_in":900,"mfa_required":false,
                   "password_setup_token":null}""",
            )
        assertNull(signedIn.passwordSetupToken)
        assertEquals("a", signedIn.accessToken)
    }

    // --- Email shape --------------------------------------------------------

    @Test
    fun `an email is checked for shape only`() {
        assertTrue(emailIsWellFormed("rafi@example.com"))
        assertTrue(emailIsWellFormed("  Rafi.Ahmed+tuition@mail.example.bd "))
        assertFalse(emailIsWellFormed("rafi.example.com"))
        assertFalse(emailIsWellFormed("rafi@example"))
        assertFalse(emailIsWellFormed("@example.com"))
        assertFalse(emailIsWellFormed("rafi@@example.com"))
        assertFalse(emailIsWellFormed("rafi ahmed@example.com"))
        assertFalse(emailIsWellFormed("rafi@example.com."))
        assertFalse(emailIsWellFormed("a@" + "b".repeat(250) + ".com"))
    }
}
