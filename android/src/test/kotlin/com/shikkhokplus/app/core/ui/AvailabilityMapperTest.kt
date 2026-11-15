package com.shikkhokplus.app.core.ui

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.UsernameAvailabilityDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The availability hint shows the server's four answers and nothing more
 * [NFR1.3, NFR6.3]: there is no state that tells taken from held, and an
 * answer this client does not understand is "could not check".
 */
class AvailabilityMapperTest {

    private fun ok(status: String, key: String? = null) = AuthResult.Ok(UsernameAvailabilityDto(status, key))

    private fun refused(key: String) = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, key)))

    @Test
    fun `available is Available`() {
        assertEquals(AvailabilityState.Available, AvailabilityMapper.afterLookup(ok("available")))
    }

    @Test
    fun `unavailable is one refusal for taken and held alike`() {
        assertEquals(
            AvailabilityState.Refused("account.username.unavailable"),
            AvailabilityMapper.afterLookup(ok("unavailable")),
        )
    }

    @Test
    fun `reserved is its own refusal`() {
        assertEquals(
            AvailabilityState.Refused("account.username.reserved"),
            AvailabilityMapper.afterLookup(ok("reserved")),
        )
    }

    @Test
    fun `invalid carries the rule the server named, for each format key`() {
        listOf(
            "account.username.too_short",
            "account.username.too_long",
            "account.username.invalid_character",
            "account.username.must_start_with_letter",
            "account.username.bad_dot",
        ).forEach { key ->
            assertEquals(AvailabilityState.Refused(key), AvailabilityMapper.afterLookup(ok("invalid", key)))
        }
    }

    @Test
    fun `invalid without a key, or a status this client does not know, could not be checked`() {
        assertEquals(AvailabilityState.CouldNotCheck, AvailabilityMapper.afterLookup(ok("invalid")))
        assertEquals(AvailabilityState.CouldNotCheck, AvailabilityMapper.afterLookup(ok("pondering")))
    }

    @Test
    fun `a 429 could not be checked, and stops checking`() {
        val tooMany = refused("auth.lookup.too_many")

        assertEquals(AvailabilityState.CouldNotCheck, AvailabilityMapper.afterLookup(tooMany))
        assertTrue(AvailabilityMapper.stopsChecking(tooMany))
    }

    @Test
    fun `any other refusal or no answer could not be checked, and checking goes on`() {
        val busy = refused("error.temporarily_unavailable")

        assertEquals(AvailabilityState.CouldNotCheck, AvailabilityMapper.afterLookup(busy))
        assertEquals(AvailabilityState.CouldNotCheck, AvailabilityMapper.afterLookup(AuthResult.TransportFailure))
        assertFalse(AvailabilityMapper.stopsChecking(busy))
        assertFalse(AvailabilityMapper.stopsChecking(AuthResult.TransportFailure))
        assertFalse(AvailabilityMapper.stopsChecking(ok("available")))
    }
}
