package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.request.get
import io.ktor.client.request.post
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withTimeout
import java.io.IOException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Cancellation is not a lost connection [NFR8.3, TSD-5].
 *
 * Before this unit the request helpers caught `Exception`, which
 * includes `CancellationException`, and turned a cancelled caller into
 * a [AuthResult.TransportFailure] it then went on to publish. A
 * superseded or timed-out username lookup would have shown "could not
 * check" over the answer that replaced it.
 *
 * Each case suspends the request inside a real [MockEngine] handler,
 * cancels the caller once the handler is reached, and asserts the caller
 * received no value at all. The last case keeps the other half honest: a
 * real transport exception is still a transport failure.
 *
 * **Real dispatchers, by necessity.** Ktor 2.3.12 deprecates the
 * engine's `dispatcher` setting (the build treats the warning as an
 * error), so the handler runs on `Dispatchers.IO`. The wait is bounded
 * by the handler signalling it was reached, never by a sleep.
 */
class CallCancellationTest {

    /** What a caller saw: nothing yet, or the value it received. */
    private object NoValue

    /**
     * Start [block] against a handler that never answers, cancel it once
     * the request is in the handler, and say what it received and
     * whether it ended cancelled.
     */
    private fun cancelWhileSuspended(block: suspend (HttpClient) -> Any?): Pair<Any?, Boolean> =
        runBlocking {
            val reached = CompletableDeferred<Unit>()
            val engine =
                MockEngine {
                    reached.complete(Unit)
                    awaitCancellation()
                }
            val client = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())
            var received: Any? = NoValue
            val job = launch(Dispatchers.Default) { received = block(client) }
            withTimeout(WAIT_MS) { reached.await() }
            job.cancelAndJoin()
            received to job.isCancelled
        }

    @Test
    fun `cancelling the caller of call propagates and returns no transport failure`() {
        val (received, cancelled) =
            cancelWhileSuspended { client -> call<IssueResponse> { client.post("/v1/auth/otp") } }

        assertTrue(cancelled)
        assertEquals(NoValue, received, "a cancelled caller was handed $received")
    }

    @Test
    fun `cancelling the caller of callDiscardingBody propagates`() {
        val (received, cancelled) =
            cancelWhileSuspended { client -> callDiscardingBody { client.post("/v1/me/notifications/read") } }

        assertTrue(cancelled)
        assertEquals(NoValue, received)
    }

    @Test
    fun `cancelling the caller of the roster read propagates`() {
        val (received, cancelled) = cancelWhileSuspended { HttpRosterRepository(it).roster("b1") }

        assertTrue(cancelled)
        assertEquals(NoValue, received)
    }

    @Test
    fun `cancelling the caller of the batch list propagates`() {
        val (received, cancelled) = cancelWhileSuspended { HttpBatchesRepository(it).batches() }

        assertTrue(cancelled)
        assertEquals(NoValue, received)
    }

    @Test
    fun `cancelling the caller of logout propagates`() {
        val (received, cancelled) =
            cancelWhileSuspended { HttpAuthRepository(it, TokenStore.InMemory()).logout("refresh") }

        assertTrue(cancelled)
        assertEquals(NoValue, received)
    }

    @Test
    fun `a real transport exception is still a transport failure`() = runTest {
        val engine = MockEngine { throw IOException("no route to host") }
        val client = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())

        assertEquals(AuthResult.TransportFailure, call<IssueResponse> { client.get("/v1/me") })
        assertEquals(AuthResult.TransportFailure, callDiscardingBody { client.post("/v1/me/notifications/read") })
        assertEquals(AuthResult.TransportFailure, HttpRosterRepository(client).roster("b1"))
        assertEquals(
            AuthResult.TransportFailure,
            HttpAuthRepository(client, TokenStore.InMemory()).logout("refresh"),
        )
    }

    private companion object {
        /** How long a handler may take to be reached before the test fails. */
        const val WAIT_MS: Long = 5_000
    }
}
