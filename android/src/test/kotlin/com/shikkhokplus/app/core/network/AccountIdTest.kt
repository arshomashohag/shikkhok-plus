package com.shikkhokplus.app.core.network

import java.util.Base64
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Reading which account a stored session belongs to [FE-2].
 *
 * The device queue binds every write to this value, so a token it
 * misreads would bind a teacher's roster to nobody -- or to someone else.
 */
class AccountIdTest {

    /** A token shaped as the server signs it: unpadded base64url segments. */
    private fun jwt(payload: String): String {
        val encoder = Base64.getUrlEncoder().withoutPadding()
        val header = encoder.encodeToString("""{"alg":"HS256","kid":"k1"}""".toByteArray())
        return "$header.${encoder.encodeToString(payload.toByteArray())}.signature"
    }

    @Test
    fun `the subject claim is the account`() {
        val account = "0d6f3c55-2b1e-4c35-9a37-6c1f5d7c2a11"

        assertEquals(account, accountIdOf(jwt("""{"sub":"$account","iat":1,"exp":2}""")))
    }

    @Test
    fun `every padding length decodes`() {
        // A JWT segment carries no padding, and its length mod 4 is
        // whatever the claims make it. Each remainder is a different
        // decoder path, and a subject of 1 to 3 extra characters walks
        // all of them.
        for (account in listOf("a", "ab", "abc", "abcd")) {
            assertEquals(account, accountIdOf(jwt("""{"sub":"$account"}""")), account)
        }
    }

    @Test
    fun `an expired token still names its account`() {
        // Offline, the stored access token is usually expired, and that
        // is exactly when the queue most needs to know whose writes it
        // holds. Nothing here reads the expiry.
        assertEquals("acc-a", accountIdOf(jwt("""{"sub":"acc-a","exp":0}""")))
    }

    @Test
    fun `an unreadable token names nobody`() {
        assertNull(accountIdOf("not-a-jwt"))
        assertNull(accountIdOf("a.%%%.c"))
        assertNull(accountIdOf(jwt("not json")))
        assertNull(accountIdOf(jwt("""["sub"]""")))
        assertNull(accountIdOf(jwt("""{"exp":2}""")))
        assertNull(accountIdOf(jwt("""{"sub":""}""")))
    }

    @Test
    fun `the token store answers from the stored access token`() {
        val tokens = TokenStore.InMemory()
        assertNull(tokens.accountId(), "signed out is nobody")

        tokens.save(jwt("""{"sub":"acc-a"}"""), "refresh")
        assertEquals("acc-a", tokens.accountId())

        tokens.clear()
        assertNull(tokens.accountId())
    }
}
