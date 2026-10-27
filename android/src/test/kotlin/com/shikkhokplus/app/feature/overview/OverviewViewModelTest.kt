package com.shikkhokplus.app.feature.overview

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MonthlyEarningsDto
import com.shikkhokplus.app.core.network.OverviewDto
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

/**
 * The today's overview ViewModel's own state machine.
 *
 * [OverviewStateMapper] covers the mapping decisions; this file covers
 * what only the ViewModel has — the loading state and the **explicit
 * retry** [TC-8, D-9] requires, because V1 has no local queue.
 *
 * **This is the half that did not exist.** The screen, its state and
 * its mapper all shipped with tests and nothing could reach the
 * server, so the screen was unreachable and its navigation tab was
 * disabled.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class OverviewViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private class FakeRepository(
        var result: AuthResult<OverviewDto> =
            AuthResult.Ok(
                OverviewDto(
                    earnings = MonthlyEarningsDto("2026-10", Money.of("4800.00")),
                ),
            ),
    ) : OverviewRepository {
        var calls = 0

        override suspend fun overview(): AuthResult<OverviewDto> {
            calls++
            return result
        }
    }

    private fun refused(
        key: String,
        retryable: Boolean,
    ) = ErrorEnvelope(ErrorBody(code = "REFUSED", messageKey = key, retryable = retryable))

    @Test
    fun `it starts loading, before anything is asked for`() {
        // A screen that opened on an empty state would tell a person
        // there is nothing to show, when nothing has been fetched yet.
        val model = OverviewViewModel(FakeRepository())

        assertEquals(OverviewUiState.Loading, model.state.value)
    }

    @Test
    fun `a successful load maps through the mapper`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = OverviewViewModel(repo)

        model.load()
        advanceUntilIdle()

        assertEquals(1, repo.calls)
        assertIs<OverviewUiState.Loaded>(model.state.value)
    }

    @Test
    fun `a refusal carries the server's own message and retryability`() =
        runTest(dispatcher) {
            // The client decides neither. Both are read from what the
            // server sent [TC-9].
            val repo =
                FakeRepository(
                    result = AuthResult.Refused(refused("error.forbidden", false)),
                )
            val model = OverviewViewModel(repo)

            model.load()
            advanceUntilIdle()

            val state = assertIs<OverviewUiState.Failed>(model.state.value)
            assertEquals("error.forbidden", state.messageKey)
            assertEquals(false, state.retryable)
        }

    @Test
    fun `a transport failure is retryable and retry repeats the call`() =
        runTest(dispatcher) {
            // **Never automatic.** There is no local queue in V1, so a
            // retry nobody asked for would be the app deciding to act
            // without connectivity.
            val repo = FakeRepository(result = AuthResult.TransportFailure)
            val model = OverviewViewModel(repo)

            model.load()
            advanceUntilIdle()

            val state = assertIs<OverviewUiState.Failed>(model.state.value)
            assertEquals(true, state.retryable)
            assertEquals(1, repo.calls)

            model.retry()
            advanceUntilIdle()
            assertEquals(2, repo.calls, "retry must repeat the call")
        }

    @Test
    fun `loading again shows the loading state rather than stale content`() =
        runTest(dispatcher) {
            // A recomposition mid-flight must not show the previous
            // answer as though it were current.
            val repo = FakeRepository()
            val model = OverviewViewModel(repo)

            model.load()
            advanceUntilIdle()
            model.load()

            assertEquals(OverviewUiState.Loading, model.state.value)
        }
}
