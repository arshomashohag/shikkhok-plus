package com.shikkhokplus.app.feature.dues

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.DuesResponseDto
import com.shikkhokplus.app.core.network.DuesRowDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
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
 * The cross-batch dues ViewModel's own state machine.
 *
 * [DuesStateMapper] covers the mapping decisions; this file covers
 * what only the ViewModel has — the loading state and the **explicit
 * retry** [TC-8, D-9] requires, because V1 has no local queue.
 *
 * **This is the half that did not exist.** The screen, its state and
 * its mapper all shipped with tests and nothing could reach the
 * server, so the screen was unreachable and its navigation tab was
 * disabled.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class DuesViewModelTest {

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
        var result: AuthResult<DuesResponseDto> = AuthResult.Ok(DuesResponseDto(
            rows =
                listOf(
                    DuesRowDto(
                        enrollmentId = "e-1",
                        batchId = "b-1",
                        batchName = "HSC Physics",
                        displayName = "Rahim",
                        outstanding = Money.of("1200.00"),
                    ),
                ),
        )),
    ) : DuesRepository {
        var calls = 0

        override suspend fun dues(): AuthResult<DuesResponseDto> {
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
        val model = DuesViewModel(FakeRepository())

        assertEquals(DuesUiState.Loading, model.state.value)
    }

    @Test
    fun `a successful load maps through the mapper`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = DuesViewModel(repo)

        model.load()
        advanceUntilIdle()

        assertEquals(1, repo.calls)
        assertIs<DuesUiState.Loaded>(model.state.value)
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
            val model = DuesViewModel(repo)

            model.load()
            advanceUntilIdle()

            val state = assertIs<DuesUiState.Failed>(model.state.value)
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
            val model = DuesViewModel(repo)

            model.load()
            advanceUntilIdle()

            val state = assertIs<DuesUiState.Failed>(model.state.value)
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
            val model = DuesViewModel(repo)

            model.load()
            advanceUntilIdle()
            model.load()

            assertEquals(DuesUiState.Loading, model.state.value)
        }
}
