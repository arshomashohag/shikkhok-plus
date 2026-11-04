package com.shikkhokplus.app.core.ui

import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class RefreshGateTest {

    /** A child scope of the test whose failures do not fail the test. */
    private fun TestScope.quietScope(): CoroutineScope =
        CoroutineScope(
            StandardTestDispatcher(testScheduler) + Job() + CoroutineExceptionHandler { _, _ -> },
        )

    @Test
    fun `the flag is up while the refresh runs and down after`() = runTest {
        val gate = RefreshGate()
        val scope = quietScope()

        assertTrue(gate.run(scope) {})
        assertTrue(gate.refreshing.value)
        advanceUntilIdle()

        assertFalse(gate.refreshing.value)
    }

    @Test
    fun `a second pull while one is in flight is dropped, not queued`() = runTest {
        val gate = RefreshGate()
        val scope = quietScope()
        var runs = 0

        assertTrue(gate.run(scope) { runs++ })
        assertFalse(gate.run(scope) { runs++ })
        advanceUntilIdle()

        assertEquals(1, runs)
        assertTrue(gate.run(scope) { runs++ }, "a new pull is accepted once the first has finished")
        advanceUntilIdle()
        assertEquals(2, runs)
    }

    @Test
    fun `a refresh that fails still lowers the flag`() = runTest {
        val gate = RefreshGate()
        val scope = quietScope()

        gate.run(scope) { error("network gone") }
        advanceUntilIdle()

        assertFalse(gate.refreshing.value)
    }

    @Test
    fun `a refresh cancelled before it starts still lowers the flag`() = runTest {
        val gate = RefreshGate()
        val scope = quietScope()
        var ran = false

        gate.run(scope) { ran = true }
        scope.cancel()
        advanceUntilIdle()

        assertFalse(ran, "the body never ran")
        assertFalse(gate.refreshing.value, "and the spinner did not stick")
    }
}
