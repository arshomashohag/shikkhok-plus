package com.shikkhokplus.app.core.ui

import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.HttpSignupRepository
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.network.UsernameAvailabilityDto
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.engine.mock.MockEngine
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * The live availability check, in virtual time [NFR8.1, NFR8.2, NFR8.3,
 * NFR2.1].
 *
 * Most cases use a fake lookup at the repository seam, so the timing is
 * the test scheduler's alone. **One case runs the real repository over a
 * [MockEngine]** whose handler never answers: Ktor 2.3.12 does not let a
 * test set the engine's dispatcher (the setting is deprecated, and the
 * build treats that as an error), but the 3-second bound is a
 * `withTimeoutOrNull` on the checker's own scope, so it still runs on
 * virtual time.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class UsernameAvailabilityCheckerTest {

    /** A lookup that records each name and answers from a table, or waits on a gate. */
    private class FakeLookup {
        val calls = mutableListOf<String>()
        val answers = mutableMapOf<String, AuthResult<UsernameAvailabilityDto>>()
        val gates = mutableMapOf<String, CompletableDeferred<AuthResult<UsernameAvailabilityDto>>>()

        suspend fun lookup(name: String): AuthResult<UsernameAvailabilityDto> {
            calls += name
            gates[name]?.let { return it.await() }
            return answers[name] ?: AuthResult.Ok(UsernameAvailabilityDto("available"))
        }
    }

    private fun TestScope.checker(fake: FakeLookup) = UsernameAvailabilityChecker(backgroundScope, fake::lookup)

    private val available = AuthResult.Ok(UsernameAvailabilityDto("available"))
    private val unavailable = AuthResult.Ok(UsernameAvailabilityDto("unavailable"))

    @Test
    fun `nothing is asked before 500 ms of quiet, and one lookup after`() = runTest {
        val fake = FakeLookup()
        val checker = checker(fake)

        checker.edited("nadia_k")
        advanceTimeBy(499)
        runCurrent()
        assertEquals(emptyList(), fake.calls)
        assertEquals(AvailabilityState.Idle, checker.state.value, "waiting shows the help line")

        advanceTimeBy(2)
        runCurrent()

        assertEquals(listOf("nadia_k"), fake.calls)
        assertEquals(AvailabilityState.Available, checker.state.value)
    }

    @Test
    fun `every edit restarts the wait, and only the last text is asked about`() = runTest {
        val fake = FakeLookup()
        val checker = checker(fake)

        checker.edited("n")
        advanceTimeBy(400)
        checker.edited("na")
        advanceTimeBy(400)
        checker.edited("nad")
        advanceTimeBy(400)
        runCurrent()
        assertEquals(emptyList(), fake.calls)

        advanceTimeBy(200)
        runCurrent()

        assertEquals(listOf("nad"), fake.calls)
    }

    @Test
    fun `an empty or blank field asks nothing and shows the help line`() = runTest {
        val fake = FakeLookup()
        val checker = checker(fake)

        checker.edited("nadia")
        checker.edited("   ")
        advanceTimeBy(1_000)
        runCurrent()

        assertEquals(emptyList(), fake.calls)
        assertEquals(AvailabilityState.Idle, checker.state.value)
    }

    @Test
    fun `a name already answered is not asked again`() = runTest {
        val fake = FakeLookup()
        fake.answers["nadia_k"] = unavailable
        val checker = checker(fake)

        checker.edited("nadia_k")
        advanceTimeBy(600)
        checker.edited("nadia_k2")
        advanceTimeBy(600)
        checker.edited(" nadia_k ")
        advanceTimeBy(600)
        runCurrent()

        assertEquals(listOf("nadia_k", "nadia_k2"), fake.calls)
        assertEquals(AvailabilityState.Refused("account.username.unavailable"), checker.state.value)
    }

    @Test
    fun `an answer for a text no longer in the field is never applied`() = runTest {
        // The older response arrives last: "ab" is slow, "abc" is quick.
        val fake = FakeLookup()
        val slow = CompletableDeferred<AuthResult<UsernameAvailabilityDto>>()
        fake.gates["ab"] = slow
        fake.answers["abc"] = unavailable
        val checker = checker(fake)

        checker.edited("ab")
        advanceTimeBy(600)
        runCurrent()
        assertEquals(AvailabilityState.Checking, checker.state.value)

        checker.edited("abc")
        advanceTimeBy(600)
        runCurrent()
        slow.complete(available)
        runCurrent()

        assertEquals(listOf("ab", "abc"), fake.calls)
        assertEquals(AvailabilityState.Refused("account.username.unavailable"), checker.state.value)
    }

    @Test
    fun `no answer is could-not-check, and nothing is asked again until the person edits`() = runTest {
        val fake = FakeLookup()
        fake.answers["nadia_k"] = AuthResult.TransportFailure
        val checker = checker(fake)

        checker.edited("nadia_k")
        advanceTimeBy(10_000)
        runCurrent()
        assertEquals(AvailabilityState.CouldNotCheck, checker.state.value)
        assertEquals(1, fake.calls.size, "no automatic retry")

        checker.edited("nadia_k1")
        advanceTimeBy(600)
        runCurrent()

        assertEquals(listOf("nadia_k", "nadia_k1"), fake.calls)
    }

    @Test
    fun `after a 429 this screen sends no lookup at all, whatever is typed`() = runTest {
        val fake = FakeLookup()
        fake.answers["nadia_k"] = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, "auth.lookup.too_many")))
        val checker = checker(fake)

        checker.edited("nadia_k")
        advanceTimeBy(600)
        runCurrent()
        checker.edited("nadia_k2")
        advanceTimeBy(600)
        checker.edited("rahim_math")
        advanceTimeBy(600)
        runCurrent()

        assertEquals(listOf("nadia_k"), fake.calls)
        assertEquals(AvailabilityState.CouldNotCheck, checker.state.value)
    }

    @Test
    fun `a lookup that never answers is could-not-check at 3 s and not before`() = runTest {
        // The real repository and client, over a handler that never answers.
        val engine = MockEngine { awaitCancellation() }
        val repository =
            HttpSignupRepository(ApiClient.build("https://staging.example", engine, TokenStore.InMemory()))
        val checker = UsernameAvailabilityChecker(backgroundScope, repository::checkUsername)

        checker.edited("nadia_k")
        advanceTimeBy(500)
        runCurrent()
        assertEquals(AvailabilityState.Checking, checker.state.value)

        advanceTimeBy(2_999)
        runCurrent()
        assertEquals(AvailabilityState.Checking, checker.state.value)

        advanceTimeBy(2)
        runCurrent()
        assertEquals(AvailabilityState.CouldNotCheck, checker.state.value)
    }

    @Test
    fun `the defaults are the design's`() {
        assertEquals(500L, UsernameAvailabilityChecker.DEBOUNCE_MS)
        assertEquals(3_000L, UsernameAvailabilityChecker.TIMEOUT_MS)
    }
}
