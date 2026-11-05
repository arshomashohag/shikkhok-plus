package com.shikkhokplus.app.core.offline

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.Serializable
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

/**
 * The phone's offline copy: written on every answer, read back only when
 * none arrives, dropped on a refusal, and never shared between accounts.
 */
class OfflineCopiesTest {

    @Serializable
    private data class Owed(val name: String, val owed: Money)

    private val store = InMemoryOfflineStore()
    private var account: String? = "acct-1"
    private var now = 1_000L
    private val copies = OfflineCopies(store, { account }, clock = { now })

    private suspend fun read(answer: AuthResult<Owed>): AuthResult<Owed> =
        copies.through("dues", Owed.serializer()) { answer }

    private val rahim = Owed("Rahim", Money.of("1200.00"))

    @Test
    fun `an answer is passed through and kept, and no answer brings it back marked saved`() = runTest {
        assertEquals(AuthResult.Ok(rahim), read(AuthResult.Ok(rahim)))

        now = 9_000L
        val offline = assertIs<AuthResult.Ok<Owed>>(read(AuthResult.TransportFailure))

        assertEquals(rahim, offline.value)
        assertEquals(1_000L, offline.savedAt, "the moment it was read, not now")
    }

    @Test
    fun `every answer overwrites the copy`() = runTest {
        read(AuthResult.Ok(rahim))
        now = 2_000L
        read(AuthResult.Ok(rahim.copy(owed = Money.of("0.00"))))

        val offline = assertIs<AuthResult.Ok<Owed>>(read(AuthResult.TransportFailure))
        assertEquals(Money.of("0.00"), offline.value.owed)
        assertEquals(2_000L, offline.savedAt)
    }

    @Test
    fun `a refusal deletes the copy, since the person may no longer see it`() = runTest {
        read(AuthResult.Ok(rahim))
        val forbidden = ErrorBody(code = "FORBIDDEN", retryable = false, messageKey = "error.forbidden")
        read(AuthResult.Refused(ErrorEnvelope(forbidden)))

        assertEquals(AuthResult.TransportFailure, read(AuthResult.TransportFailure))
    }

    @Test
    fun `one account never reads another's copy, and nobody signed in keeps nothing`() = runTest {
        read(AuthResult.Ok(rahim))

        account = "acct-2"
        assertEquals(AuthResult.TransportFailure, read(AuthResult.TransportFailure))

        account = null
        read(AuthResult.Ok(rahim))
        assertEquals(AuthResult.TransportFailure, read(AuthResult.TransportFailure))
    }

    @Test
    fun `a copy in a shape this build cannot read is forgotten, not a crash`() = runTest {
        store.put("acct-1/dues", "{\"savedAt\":1,\"value\":{\"name\":\"Rahim\",\"owed\":1200}}")

        assertEquals(AuthResult.TransportFailure, read(AuthResult.TransportFailure))
        assertNull(store.get("acct-1/dues"))
    }

    @Test
    fun `sign-out clears every copy`() = runTest {
        read(AuthResult.Ok(rahim))
        copies.clear()

        assertEquals(AuthResult.TransportFailure, read(AuthResult.TransportFailure))
    }
}
