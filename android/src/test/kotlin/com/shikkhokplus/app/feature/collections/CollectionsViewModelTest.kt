package com.shikkhokplus.app.feature.collections

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.yield
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
import kotlin.test.assertTrue

/** The collections screen's state machine (M1). */
@OptIn(ExperimentalCoroutinesApi::class)
class CollectionsViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun loaded(model: CollectionsViewModel) = assertIs<CollectionsUiState.Loaded>(model.state.value)

    @Test
    fun `it starts loading`() {
        assertIs<CollectionsUiState.Loading>(CollectionsViewModel(FakeCollectionsRepository()).state.value)
    }

    @Test
    fun batch_chips_refetch_with_selected_ids() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository()
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()
            assertEquals(listOf(emptyList()), repo.reportCalls)

            model.toggle("b-2")
            advanceUntilIdle()
            model.toggle("b-1")
            advanceUntilIdle()
            model.toggle("b-2")
            advanceUntilIdle()

            assertEquals(
                listOf(emptyList(), listOf("b-2"), listOf("b-2", "b-1"), listOf("b-1")),
                repo.reportCalls,
            )
            assertEquals(listOf(true), loaded(model).batches.filter { it.selected }.map { it.id == "b-1" })
        }

    @Test
    fun in_progress_month_is_marked() =
        runTest(dispatcher) {
            val model = CollectionsViewModel(FakeCollectionsRepository())
            model.load()
            advanceUntilIdle()

            val months = loaded(model).months
            assertEquals(listOf(false, true), months.map { it.inProgress })
            assertEquals("2026-10", loaded(model).headlinePeriod)
        }

    @Test
    fun `bars carry the server's whole percents and nothing else`() =
        runTest(dispatcher) {
            val model = CollectionsViewModel(FakeCollectionsRepository())
            model.load()
            advanceUntilIdle()

            val bar = loaded(model).months.first()
            assertEquals(100, bar.chargedBar)
            assertEquals(60, bar.collectedBar)
            assertEquals(Money.of("9500.00"), loaded(model).outstanding)
            assertEquals(11, loaded(model).owingStudents)
        }

    @Test
    fun `each batch in view gets a row for the headline month from the server`() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository()
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()

            assertEquals(listOf<Pair<String, String?>>("b-1" to "2026-10", "b-2" to "2026-10"), repo.monthCalls)
            assertEquals(listOf("Physics", "Math"), loaded(model).batchRows.map { it.name })
        }

    @Test
    fun `a refusal fails with the server's key and retryability, and retry asks again`() =
        runTest(dispatcher) {
            val repo =
                FakeCollectionsRepository(
                    report = AuthResult.Refused(refusal("error.transient", retryable = true)),
                )
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()
            val failed = assertIs<CollectionsUiState.Failed>(model.state.value)
            assertEquals("error.transient", failed.messageKey)
            assertTrue(failed.retryable)

            model.retry()
            advanceUntilIdle()
            assertEquals(2, repo.reportCalls.size)
        }

    @Test
    fun `an unreachable server is a retryable offline failure`() =
        runTest(dispatcher) {
            val model = CollectionsViewModel(FakeCollectionsRepository(batches = AuthResult.TransportFailure))
            model.load()
            advanceUntilIdle()
            val failed = assertIs<CollectionsUiState.Failed>(model.state.value)
            assertEquals("error.network.unreachable", failed.messageKey)
            assertTrue(failed.retryable)
        }

    @Test
    fun `no months means no headline and no rows`() =
        runTest(dispatcher) {
            val repo =
                FakeCollectionsRepository(
                    report =
                        AuthResult.Ok(
                            com.shikkhokplus.app.core.network.CollectionsDto(
                                months = emptyList(),
                                outstanding = Money.ZERO,
                                owingStudents = 0,
                            ),
                        ),
                )
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()
            assertEquals(null, loaded(model).headlinePeriod)
            assertFalse(loaded(model).batchRows.isNotEmpty())
        }

    @Test
    fun `choosing a month moves the tiles and the batch rows to it`() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository()
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()

            model.selectMonth("2026-11")
            advanceUntilIdle()

            assertEquals("2026-11", loaded(model).headlinePeriod)
            assertEquals("2026-11", assertIs<BatchMonthRow>(loaded(model).batchRows.first()).period)
            assertEquals("2026-11", repo.monthCalls.last().second)
        }

    @Test
    fun `show all clears the narrowing and asks again with no ids`() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository()
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()
            model.showAll()
            advanceUntilIdle()
            assertEquals(1, repo.reportCalls.size)

            model.toggle("b-1")
            advanceUntilIdle()
            model.showAll()
            advanceUntilIdle()

            assertEquals(listOf(emptyList(), listOf("b-1"), emptyList()), repo.reportCalls)
            assertTrue(loaded(model).batches.none { it.selected })
        }

    @Test
    fun `one failing batch degrades only its own row`() =
        runTest(dispatcher) {
            val repo =
                FakeCollectionsRepository(
                    month = { id, period ->
                        if (id == "b-2") {
                            AuthResult.Refused(refusal("error.transient", retryable = true))
                        } else {
                            AuthResult.Ok(monthFees(period ?: "2026-10"))
                        }
                    },
                )
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()

            val state = loaded(model)
            assertEquals(2, state.months.size)
            assertEquals(Money.of("9500.00"), state.outstanding)
            assertIs<BatchMonthRow>(state.batchRows[0])
            val failed = assertIs<BatchRowFailed>(state.batchRows[1])
            assertEquals("b-2", failed.batchId)
            assertEquals("error.transient", failed.messageKey)
            assertTrue(failed.retryable)
        }

    @Test
    fun `an unreachable batch row is a retryable row failure`() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository(month = { _, _ -> AuthResult.TransportFailure })
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()

            val rows = loaded(model).batchRows
            assertTrue(rows.all { it is BatchRowFailed && it.retryable })
            assertEquals("error.network.unreachable", (rows[0] as BatchRowFailed).messageKey)
        }

    @Test
    fun `retrying a row refetches only that batch and leaves the rest alone`() =
        runTest(dispatcher) {
            var failB2 = true
            val repo =
                FakeCollectionsRepository(
                    month = { id, period ->
                        if (id == "b-2" && failB2) {
                            AuthResult.TransportFailure
                        } else {
                            AuthResult.Ok(monthFees(period ?: "2026-10"))
                        }
                    },
                )
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()
            val reportCalls = repo.reportCalls.size
            repo.monthCalls.clear()

            failB2 = false
            model.retryBatch("b-2")
            advanceUntilIdle()

            assertEquals(listOf<Pair<String, String?>>("b-2" to "2026-10"), repo.monthCalls)
            assertEquals(reportCalls, repo.reportCalls.size)
            assertTrue(loaded(model).batchRows.all { it is BatchMonthRow })
            assertEquals(listOf("b-1", "b-2"), loaded(model).batchRows.map { it.batchId })
        }

    @Test
    fun `retrying a row that fails again keeps it failed, and retrying nothing is a no-op`() =
        runTest(dispatcher) {
            val repo = FakeCollectionsRepository(month = { _, _ -> AuthResult.TransportFailure })
            val model = CollectionsViewModel(repo)
            model.retryBatch("b-1")
            advanceUntilIdle()
            assertEquals(0, repo.monthCalls.size)

            model.load()
            advanceUntilIdle()
            model.retryBatch("b-1")
            advanceUntilIdle()
            assertIs<BatchRowFailed>(loaded(model).batchRows[0])
        }

    @Test
    fun `batch rows are fetched concurrently`() =
        runTest(dispatcher) {
            var active = 0
            var peak = 0
            val repo =
                FakeCollectionsRepository(
                    onMonth = {
                        active++
                        peak = maxOf(peak, active)
                        yield()
                        active--
                    },
                )
            val model = CollectionsViewModel(repo)
            model.load()
            advanceUntilIdle()
            assertEquals(2, peak)
        }
}
