package com.shikkhokplus.app.feature.fees

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.FeeCycleDto
import com.shikkhokplus.app.core.network.FeeHistoryDto
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
 * The fee history ViewModel's own state machine.
 *
 * [FeeStateMapperTest] covers the mapping; this covers the loading
 * state, the explicit retry, and **which route each lens reads
 * through** — three paths for one shape, because the server resolves
 * a different lens for each [BR6.3].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class FeesViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun history(total: String = "1200.00") =
        FeeHistoryDto(
            cycles =
                listOf(
                    FeeCycleDto(
                        period = "2026-10",
                        dueDate = "2026-10-10",
                        charged = Money.of("1200.00"),
                        outstanding = Money.of("1200.00"),
                        status = "unpaid",
                    ),
                ),
            totalOutstanding = Money.of(total),
        )

    private class FakeRepository(
        var result: AuthResult<FeeHistoryDto>,
    ) : FeesRepository {
        var mine = 0
        var child = 0
        var enrollment = 0

        override suspend fun myFees(enrollmentId: String): AuthResult<FeeHistoryDto> {
            mine++
            return result
        }

        override suspend fun childFees(enrollmentId: String): AuthResult<FeeHistoryDto> {
            child++
            return result
        }

        override suspend fun enrollmentFees(
            enrollmentId: String,
        ): AuthResult<FeeHistoryDto> {
            enrollment++
            return result
        }
    }

    @Test
    fun `each reader uses its own route and no other`() = runTest(dispatcher) {
        // **One route per lens, and the client picks none of them by
        // role.** A single route taking a role parameter would be the
        // client choosing which lens to be [TC-11, D-2].
        val repo = FakeRepository(AuthResult.Ok(history()))
        val model = FeesViewModel(repo)

        model.load("e-1", FeeReader.STUDENT)
        advanceUntilIdle()
        assertEquals(1, repo.mine)
        assertEquals(0, repo.child)
        assertEquals(0, repo.enrollment)

        model.load("e-1", FeeReader.GUARDIAN)
        advanceUntilIdle()
        assertEquals(1, repo.child)

        model.load("e-1", FeeReader.TEACHER)
        advanceUntilIdle()
        assertEquals(1, repo.enrollment)
        assertEquals(1, repo.mine, "a later read must not repeat an earlier route")
    }

    @Test
    fun `the total comes from the server, not from summing the rows`() =
        runTest(dispatcher) {
            // **The defect this prevents.** Summing the rows would be
            // money arithmetic on the client [D-20], and it would be
            // wrong the moment the history paginates. The fixture's
            // total deliberately differs from its single row, so a
            // client-side sum would produce 1200 and fail here.
            val repo = FakeRepository(AuthResult.Ok(history(total = "7200.00")))
            val model = FeesViewModel(repo)

            model.load("e-1", FeeReader.STUDENT)
            advanceUntilIdle()

            val state = assertIs<FeeUiState.Loaded>(model.state.value)
            assertEquals(Money.of("7200.00"), state.totalOutstanding)
        }

    @Test
    fun `it starts loading rather than empty`() {
        val model = FeesViewModel(FakeRepository(AuthResult.Ok(history())))
        assertEquals(FeeUiState.Loading, model.state.value)
    }

    @Test
    fun `no periods is its own state, not a loaded list of none`() =
        runTest(dispatcher) {
            val repo =
                FakeRepository(
                    AuthResult.Ok(
                        FeeHistoryDto(totalOutstanding = Money.of("0.00")),
                    ),
                )
            val model = FeesViewModel(repo)

            model.load("e-1", FeeReader.STUDENT)
            advanceUntilIdle()

            assertEquals(FeeUiState.Empty, model.state.value)
        }

    @Test
    fun `a refusal carries the server's own message and retryability`() =
        runTest(dispatcher) {
            val repo =
                FakeRepository(
                    AuthResult.Refused(
                        ErrorEnvelope(
                            ErrorBody(
                                code = "FORBIDDEN",
                                messageKey = "error.forbidden",
                                retryable = false,
                            ),
                        ),
                    ),
                )
            val model = FeesViewModel(repo)

            model.load("e-1", FeeReader.STUDENT)
            advanceUntilIdle()

            val state = assertIs<FeeUiState.Failed>(model.state.value)
            assertEquals("error.forbidden", state.messageKey)
            assertEquals(false, state.retryable)
        }

    @Test
    fun `a transport failure is retryable and retry repeats the same route`() =
        runTest(dispatcher) {
            val repo = FakeRepository(AuthResult.TransportFailure)
            val model = FeesViewModel(repo)

            model.load("e-1", FeeReader.GUARDIAN)
            advanceUntilIdle()

            val state = assertIs<FeeUiState.Failed>(model.state.value)
            assertEquals(true, state.retryable)

            model.retry()
            advanceUntilIdle()
            assertEquals(2, repo.child, "retry must repeat the guardian route")
            assertEquals(0, repo.mine, "retry must not change lens")
        }
}
