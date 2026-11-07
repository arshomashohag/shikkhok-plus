package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerializationException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The two-step verification wire shapes [0028], decoded and encoded with
 * the app's real [ApiClient.json].
 */
class MfaDtoTest {

    private val json = ApiClient.json

    @Test
    fun `a verify for an account without two-step verification is the pair, as before`() {
        val decoded =
            json.decodeFromString(
                VerifyResponse.serializer(),
                """{"access_token":"a.b.c","refresh_token":"r1","expires_in":900,"mfa_required":false}""",
            )

        assertEquals("a.b.c", decoded.accessToken)
        assertEquals("r1", decoded.refreshToken)
        assertEquals(900, decoded.expiresIn)
        assertFalse(decoded.mfaRequired)
        assertNull(decoded.mfaChallenge)
    }

    @Test
    fun `a verify from a server older than the second step reads as no second step`() {
        // The old shape carries no `mfa_required` at all.
        val decoded =
            json.decodeFromString(
                VerifyResponse.serializer(),
                """{"access_token":"a.b.c","refresh_token":"r1","expires_in":900}""",
            )

        assertFalse(decoded.mfaRequired)
        assertEquals("a.b.c", decoded.accessToken)
    }

    @Test
    fun `a verify for an account with two-step verification carries a challenge and no pair`() {
        val decoded =
            json.decodeFromString(
                VerifyResponse.serializer(),
                """{"access_token":null,"refresh_token":null,"expires_in":null,
                "mfa_required":true,"mfa_challenge":"chal.lenge","mfa_expires_in":300}""",
            )

        assertTrue(decoded.mfaRequired)
        assertEquals("chal.lenge", decoded.mfaChallenge)
        assertEquals(300, decoded.mfaExpiresIn)
        assertNull(decoded.accessToken)
        assertNull(decoded.refreshToken)
    }

    @Test
    fun `the token fields may be absent rather than null`() {
        val decoded =
            json.decodeFromString(
                VerifyResponse.serializer(),
                """{"mfa_required":true,"mfa_challenge":"c","mfa_expires_in":300}""",
            )

        assertNull(decoded.accessToken)
        assertTrue(decoded.mfaRequired)
    }

    @Test
    fun `the second step sends the challenge and only the code it has`() {
        assertEquals(
            """{"challenge":"c","code":"123456"}""",
            json.encodeToString(MfaSignInRequest.serializer(), MfaSignInRequest("c", code = "123456")),
        )
        assertEquals(
            """{"challenge":"c","recovery_code":"ABCDE-FGHJK"}""",
            json.encodeToString(MfaSignInRequest.serializer(), MfaSignInRequest("c", recoveryCode = "ABCDE-FGHJK")),
        )
    }

    @Test
    fun `the status decodes, with enabled_at null or absent`() {
        val on =
            json.decodeFromString(
                MfaStatusDto.serializer(),
                """{"enabled":true,"enabled_at":"2026-11-06T04:00:00Z","recovery_codes_left":7,
                "recommended":true,"required":false}""",
            )
        val off =
            json.decodeFromString(
                MfaStatusDto.serializer(),
                """{"enabled":false,"recovery_codes_left":0,"recommended":false,"required":false}""",
            )

        assertEquals(MfaStatusDto(true, "2026-11-06T04:00:00Z", 7, recommended = true, required = false), on)
        assertNull(off.enabledAt)
        assertFalse(off.enabled)
    }

    @Test
    fun `a status missing a field the server always sends fails loudly`() {
        // `required` hides Turn off; a silent default would offer a
        // platform administrator a button the server refuses.
        assertFailsWith<SerializationException> {
            json.decodeFromString(
                MfaStatusDto.serializer(),
                """{"enabled":true,"recovery_codes_left":7,"recommended":false}""",
            )
        }
    }

    @Test
    fun `a field the server adds later is tolerated`() {
        val decoded =
            json.decodeFromString(
                MfaSetupDto.serializer(),
                """{"secret":"JBSWY3DPEHPK3PXP","otpauth_uri":"otpauth://totp/x","issuer":"ShikkhokPlus"}""",
            )

        assertEquals("JBSWY3DPEHPK3PXP", decoded.secret)
        assertEquals("otpauth://totp/x", decoded.otpauthUri)
    }

    @Test
    fun `recovery codes decode in the server's order`() {
        val decoded =
            json.decodeFromString(
                MfaRecoveryCodesDto.serializer(),
                """{"recovery_codes":["AAAAA-BBBBB","CCCCC-DDDDD"]}""",
            )

        assertEquals(listOf("AAAAA-BBBBB", "CCCCC-DDDDD"), decoded.recoveryCodes)
    }

    @Test
    fun `turning off sends exactly one of the two codes`() {
        assertEquals(
            """{"code":"123456"}""",
            json.encodeToString(MfaProofRequestDto.serializer(), MfaProofRequestDto(code = "123456")),
        )
        assertEquals(
            """{"recovery_code":"ABCDE-FGHJK"}""",
            json.encodeToString(MfaProofRequestDto.serializer(), MfaProofRequestDto(recoveryCode = "ABCDE-FGHJK")),
        )
        assertEquals(
            """{"code":"654321"}""",
            json.encodeToString(MfaCodeRequestDto.serializer(), MfaCodeRequestDto("654321")),
        )
    }
}
