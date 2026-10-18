package com.shikkhokplus.app.feature.roster

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RosterRowDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * The roster ViewModel's state machine.
 *
 * `team.md` requires every ViewModel to ship tests for loading,
 * success, error, and **the explicit retry path for a failed write**
 * [TC-8, D-9] — V1 accepts no write without connectivity and has no
 * local queue, so a failed removal must surface rather than appear to
 * have worked.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class RosterViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun row(
        name: String,
        status: String = "active",
    ): RosterRowDto =
        RosterRowDto(
            enrollmentId = "e-$name",
            displayName = name,
            status = status,
        )

    private class FakeRepository(
        var rosterResult: AuthResult<RosterPayload> =
            AuthResult.Ok(RosterPayload("Physics", emptyList())),
        var removeResult: AuthResult<Unit> = AuthResult.Ok(Unit),
    ) : RosterRepository {
        var rosterCalls = 0
        var removeCalls = 0
        var lastRemoved: String? = null

        override suspend fun roster(batchId: String): AuthResult<RosterPayload> {
            rosterCalls += 1
            return rosterResult
        }

        override suspend fun removeEnrollment(enrollmentId: String): AuthResult<Unit> {
            removeCalls += 1
            lastRemoved = enrollmentId
            return removeResult
        }
    }

    @Test
    fun `starts idle`() {
        val viewModel = RosterViewModel(FakeRepository())

        assertEquals(RosterUiState.Idle, viewModel.state.value)
    }

    @Test
    fun `shows loading while the request is in flight`() = runTest(dispatcher) {
        val viewModel = RosterViewModel(FakeRepository())

        viewModel.load("b-1")

        assertEquals(RosterUiState.Loading, viewModel.state.value)
    }

    @Test
    fun `a loaded roster becomes Loaded`() = runTest(dispatcher) {
        val repository =
            FakeRepository(
                rosterResult =
                    AuthResult.Ok(RosterPayload("Physics", listOf(row("Rahim")))),
            )
        val viewModel = RosterViewModel(repository)

        viewModel.load("b-1")
        advanceUntilIdle()

        val state = assertIs<RosterUiState.Loaded>(viewModel.state.value)
        assertEquals("Physics", state.batchName)
        assertEquals(listOf("Rahim"), state.rows.map { it.displayName })
    }

    @Test
    fun `an empty roster is its own state, not a Loaded with no rows`() =
        runTest(dispatcher) {
            // An empty list and "no students yet" need different screens,
            // and a blank list explains neither.
            val viewModel = RosterViewModel(FakeRepository())

            viewModel.load("b-1")
            advanceUntilIdle()

            assertIs<RosterUiState.Empty>(viewModel.state.value)
        }

    @Test
    fun `a server refusal reads retryable from the envelope`() = runTest(dispatcher) {
        // Never inferred from a status code: the client holds no business
        // logic, so it is TOLD whether a retry is appropriate [TC-9].
        val repository =
            FakeRepository(
                rosterResult =
                    AuthResult.Refused(
                        ErrorEnvelope(
                            ErrorBody(
                                code = "BATCH_NOT_FOUND",
                                retryable = false,
                                messageKey = "batch.not_found",
                            ),
                        ),
                    ),
            )
        val viewModel = RosterViewModel(repository)

        viewModel.load("b-1")
        advanceUntilIdle()

        val state = assertIs<RosterUiState.Failed>(viewModel.state.value)
        assertEquals("batch.not_found", state.messageKey)
        assertEquals(false, state.retryable)
    }

    @Test
    fun `a transport failure is retryable and names a string key`() =
        runTest(dispatcher) {
            val repository =
                FakeRepository(rosterResult = AuthResult.TransportFailure)
            val viewModel = RosterViewModel(repository)

            viewModel.load("b-1")
            advanceUntilIdle()

            val state = assertIs<RosterUiState.Failed>(viewModel.state.value)
            assertEquals(RosterStateMapper.OFFLINE_KEY, state.messageKey)
            assertTrue(state.retryable)
        }

    @Test
    fun `a failed removal surfaces and is not queued locally`() = runTest(dispatcher) {
        // THE RULE [TC-8, D-9]: there is no local write queue in V1, so a
        // failed removal must NOT look like it worked. The seat stays and
        // the screen says so.
        val repository =
            FakeRepository(removeResult = AuthResult.TransportFailure)
        val viewModel = RosterViewModel(repository)

        viewModel.remove("e-Rahim")
        advanceUntilIdle()

        val state = assertIs<RosterUiState.Failed>(viewModel.state.value)
        assertTrue(state.retryable)
        assertEquals(1, repository.removeCalls)
    }

    @Test
    fun `retry after a failed removal repeats the REMOVAL, not a reload`() =
        runTest(dispatcher) {
            // The defect this catches: a retry that degrades into a reload
            // silently drops the user's intent. The seat stays, the error
            // clears, and nothing on screen says the removal never happened.
            val repository =
                FakeRepository(removeResult = AuthResult.TransportFailure)
            val viewModel = RosterViewModel(repository)

            viewModel.load("b-1")
            advanceUntilIdle()
            viewModel.remove("e-Rahim")
            advanceUntilIdle()

            viewModel.retry()
            advanceUntilIdle()

            assertEquals(2, repository.removeCalls)
            assertEquals("e-Rahim", repository.lastRemoved)
        }

    @Test
    fun `retry runs only when asked`() = runTest(dispatcher) {
        // No silent retry: a request is made once and the user decides.
        val repository =
            FakeRepository(rosterResult = AuthResult.TransportFailure)
        val viewModel = RosterViewModel(repository)

        viewModel.load("b-1")
        advanceUntilIdle()

        assertEquals(1, repository.rosterCalls)
    }

    @Test
    fun `a successful removal reloads the roster`() = runTest(dispatcher) {
        val repository = FakeRepository()
        val viewModel = RosterViewModel(repository)

        viewModel.load("b-1")
        advanceUntilIdle()
        viewModel.remove("e-Rahim")
        advanceUntilIdle()

        assertEquals(2, repository.rosterCalls)
    }
}
