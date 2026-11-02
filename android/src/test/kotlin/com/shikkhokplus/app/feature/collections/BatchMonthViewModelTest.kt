package com.shikkhokplus.app.feature.collections

import com.shikkhokplus.app.core.model.ClaimOutcome
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.HistoryLineDto
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
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** The batch-month screen's state machine (M2). */
@OptIn(ExperimentalCoroutinesApi::class)
class BatchMonthViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun loaded(model: BatchMonthViewModel) = assertIs<BatchMonthUiState.Loaded>(model.state.value)

    private val seats =
        listOf(
            seatDto("a", "unpaid", days = 22),
            seatDto("b", "unpaid"),
            seatDto("c", "checking"),
            seatDto("d", "paid"),
            seatDto("e", "waived"),
            seatDto("f", "partly_paid"),
            seatDto("g", null),
        )

    @Test
    fun batch_month_switch_requests_period() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository(month = { _, period -> AuthResult.Ok(monthFees(period ?: "2026-11")) })
            val model = BatchMonthViewModel(repo)
            model.load("b-1")
            advanceUntilIdle()
            assertEquals("2026-11", loaded(model).period)
            assertFalse(loaded(model).canGoNext)

            model.previous()
            advanceUntilIdle()
            assertEquals("2026-10", loaded(model).period)
            assertTrue(loaded(model).canGoNext)

            model.next()
            advanceUntilIdle()

            assertEquals(
                listOf<Pair<String, String?>>("b-1" to null, "b-1" to "2026-10", "b-1" to "2026-11"),
                repo.monthCalls,
            )
        }

    @Test
    fun `previous steps back across a year`() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository()
            val model = BatchMonthViewModel(repo)
            model.load("b-1", "2026-01")
            advanceUntilIdle()
            model.previous()
            advanceUntilIdle()
            assertEquals("2025-12", repo.monthCalls.last().second)
        }

    @Test
    fun filters_use_server_counts() =
        runTest(dispatcher) {
            val repo =
                FakeCollectionsRepository(
                    month = { _, _ -> AuthResult.Ok(monthFees("2026-11", seats, paid = 9, checking = 1, owed = 2)) },
                )
            val model = BatchMonthViewModel(repo)
            model.load("b-1")
            advanceUntilIdle()

            assertEquals(SeatCounts(paid = 9, checking = 1, owed = 2), loaded(model).counts)

            model.filter(MonthFilter.OWED)
            assertEquals(listOf("a", "b", "f"), loaded(model).seats.map { it.enrollmentId })
            assertEquals(SeatCounts(paid = 9, checking = 1, owed = 2), loaded(model).counts)

            model.filter(MonthFilter.PAID)
            assertEquals(listOf("d", "e"), loaded(model).seats.map { it.enrollmentId })

            model.filter(MonthFilter.CHECKING)
            assertEquals(listOf("c"), loaded(model).seats.map { it.enrollmentId })

            model.filter(MonthFilter.ALL)
            assertEquals(7, loaded(model).seats.size)
        }

    @Test
    fun `a seat's kind is chosen from the server's state and day count`() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository(month = { _, _ -> AuthResult.Ok(monthFees("2026-11", seats)) })
            val model = BatchMonthViewModel(repo)
            model.load("b-1")
            advanceUntilIdle()
            assertEquals(
                listOf(
                    SeatKind.OVERDUE,
                    SeatKind.DUE,
                    SeatKind.CHECKING,
                    SeatKind.PAID,
                    SeatKind.WAIVED,
                    SeatKind.PARTIAL,
                    SeatKind.NONE,
                ),
                loaded(model).seats.map { it.kind },
            )
        }

    @Test
    fun `a history line stays structured and an unknown status reads as pending`() =
        runTest(dispatcher) {
            val rejected = HistoryLineDto(Money.of("1000.00"), "bKash", "2026-10-28", "rejected", "TrxID not found")
            val odd = HistoryLineDto(Money.of("5.00"), "cash", "2026-10-01", "mystery")
            val repo =
                FakeCollectionsRepository(
                    month = { _, _ ->
                        AuthResult.Ok(
                            monthFees(
                                "2026-10",
                                listOf(seatDto("a", "unpaid", line = rejected), seatDto("b", "paid", line = odd)),
                            ),
                        )
                    },
                )
            val model = BatchMonthViewModel(repo)
            model.load("b-1", "2026-10")
            advanceUntilIdle()

            val first = loaded(model).seats[0].historyLine!!
            assertEquals(ClaimOutcome.REJECTED, first.outcome)
            assertEquals("TrxID not found", first.decisionNote)
            assertEquals(Money.of("1000.00"), first.amount)
            assertEquals(ClaimOutcome.PENDING, loaded(model).seats[1].historyLine!!.outcome)
            assertNull(loaded(model).seats[1].historyLine!!.decisionNote)
        }

    @Test
    fun `the filter survives a month switch`() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository(month = { _, _ -> AuthResult.Ok(monthFees("2026-10", seats)) })
            val model = BatchMonthViewModel(repo)
            model.load("b-1", "2026-10")
            advanceUntilIdle()
            model.filter(MonthFilter.CHECKING)
            model.previous()
            advanceUntilIdle()
            assertEquals(MonthFilter.CHECKING, loaded(model).filter)
            assertEquals(listOf("c"), loaded(model).seats.map { it.enrollmentId })
        }

    @Test
    fun `failures carry the server's key, and retry asks again`() =
        runTest(dispatcher) {
            var refuse = true
            val repo =
                FakeCollectionsRepository(
                    month = { _, _ ->
                        if (refuse) {
                            AuthResult.Refused(refusal("error.transient", retryable = true))
                        } else {
                            AuthResult.Ok(monthFees("2026-11"))
                        }
                    },
                )
            val model = BatchMonthViewModel(repo)
            model.load("b-1")
            advanceUntilIdle()
            assertEquals("error.transient", assertIs<BatchMonthUiState.Failed>(model.state.value).messageKey)

            refuse = false
            model.retry()
            advanceUntilIdle()
            assertIs<BatchMonthUiState.Loaded>(model.state.value)
        }

    @Test
    fun `an unreachable server is a retryable failure and switching before loading does nothing`() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository(month = { _, _ -> AuthResult.TransportFailure })
            val model = BatchMonthViewModel(repo)
            model.previous()
            model.next()
            model.filter(MonthFilter.OWED)
            assertEquals(0, repo.monthCalls.size)

            model.load("b-1")
            advanceUntilIdle()
            val failed = assertIs<BatchMonthUiState.Failed>(model.state.value)
            assertEquals("error.network.unreachable", failed.messageKey)
            assertTrue(failed.retryable)
        }
}
