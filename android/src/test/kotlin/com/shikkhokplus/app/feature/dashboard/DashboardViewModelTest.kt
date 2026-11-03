package com.shikkhokplus.app.feature.dashboard

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.DashboardFeeMonthDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.fees.StripKind
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
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
import kotlin.test.assertTrue

/** The progress dashboard's state machine (D1, D2). */
@OptIn(ExperimentalCoroutinesApi::class)
class DashboardViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun loaded(model: DashboardViewModel) = assertIs<DashboardUiState.Loaded>(model.state.value)

    @Test
    fun range_chip_refetches() =
        runTest(dispatcher) {
            val repo = FakeDashboardRepository()
            val model = DashboardViewModel(repo)
            model.load(DashboardReader.TEACHER, "e-1", "Sadia", "Physics")
            advanceUntilIdle()

            model.selectRange(DashboardRange.YEAR)
            advanceUntilIdle()
            model.selectRange(DashboardRange.YEAR)
            advanceUntilIdle()

            assertEquals(
                listOf(DashboardRange.SIX_MONTHS, DashboardRange.YEAR),
                repo.calls.map { it.third },
            )
            assertEquals(DashboardRange.YEAR, loaded(model).range)
            assertEquals("Sadia", loaded(model).heading)
            assertFalse(loaded(model).refreshing)
        }

    @Test
    fun guardian_switching_child_refetches() =
        runTest(dispatcher) {
            val repo = FakeDashboardRepository()
            val model = DashboardViewModel(repo)
            model.load(DashboardReader.GUARDIAN, "s-1")
            advanceUntilIdle()
            assertEquals("Tanvir", loaded(model).heading)
            assertEquals(2, loaded(model).batches.size)

            model.selectChild("s-3")
            advanceUntilIdle()

            assertEquals(listOf("s-1", "s-3"), repo.calls.map { it.second })
            assertEquals("Tania", loaded(model).heading)
            assertEquals("s-3", loaded(model).seat)
            assertTrue(repo.calls.all { it.first == DashboardReader.GUARDIAN })
        }

    @Test
    fun `guardian batch picker refetches the other batch`() =
        runTest(dispatcher) {
            val repo = FakeDashboardRepository()
            val model = DashboardViewModel(repo)
            model.load(DashboardReader.GUARDIAN, "s-1")
            advanceUntilIdle()

            model.selectBatch("s-2")
            advanceUntilIdle()

            assertEquals("Math", loaded(model).subheading)
            assertEquals("s-2", repo.calls.last().second)
        }

    @Test
    fun `figures are the server's, money included`() =
        runTest(dispatcher) {
            val model = DashboardViewModel(FakeDashboardRepository())
            model.load(DashboardReader.STUDENT, "e-1")
            advanceUntilIdle()

            val state = loaded(model)
            assertEquals(Money.of("2000.00"), state.owed)
            assertEquals(86, state.attendancePercent)
            assertEquals(DashboardDirection.UP, state.direction)
            assertEquals(listOf(StripKind.PAID, StripKind.UNPAID), state.feeMonths.map { it.kind })
            assertTrue(state.canSendMoney)
        }

    @Test
    fun `a teacher cannot send money from here`() =
        runTest(dispatcher) {
            val model = DashboardViewModel(FakeDashboardRepository())
            model.load(DashboardReader.TEACHER, "e-1")
            advanceUntilIdle()

            assertFalse(loaded(model).canSendMoney)
        }

    @Test
    fun `an unknown fee state is dropped rather than drawn wrongly`() =
        runTest(dispatcher) {
            val base = dashboardDto()
            val dto = base.copy(feeMonths = base.feeMonths + DashboardFeeMonthDto("2026-12", "mystery"))
            val model = DashboardViewModel(FakeDashboardRepository(result = AuthResult.Ok(dto)))
            model.load(DashboardReader.STUDENT, "e-1")
            advanceUntilIdle()

            assertEquals(2, loaded(model).feeMonths.size)
        }

    @Test
    fun `a refusal carries the server's retryable and retry reads again`() =
        runTest(dispatcher) {
            val repo = FakeDashboardRepository(result = AuthResult.Refused(dashboardRefusal("k", true)))
            val model = DashboardViewModel(repo)
            model.load(DashboardReader.STUDENT, "e-1")
            advanceUntilIdle()
            assertEquals(DashboardUiState.Failed("k", true), model.state.value)

            repo.result = AuthResult.Ok(dashboardDto())
            model.retry()
            advanceUntilIdle()

            loaded(model)
            assertEquals(2, repo.calls.size)
        }

    @Test
    fun `a transport failure is offline and retryable`() =
        runTest(dispatcher) {
            val repo = FakeDashboardRepository(result = AuthResult.TransportFailure)
            val model = DashboardViewModel(repo)
            model.load(DashboardReader.STUDENT, "e-1")
            advanceUntilIdle()

            assertEquals(DashboardUiState.Failed("error.network.unreachable", true), model.state.value)
        }

    @Test
    fun `a guardian seat that is not theirs is not available`() =
        runTest(dispatcher) {
            val repo = FakeDashboardRepository()
            val model = DashboardViewModel(repo)
            model.load(DashboardReader.GUARDIAN, "someone-else")
            advanceUntilIdle()

            assertEquals(DashboardUiState.Failed("error.not_available", false), model.state.value)
            assertTrue(repo.calls.isEmpty())
        }

    @Test
    fun `a failed children read fails the screen`() =
        runTest(dispatcher) {
            val repo = FakeDashboardRepository(home = AuthResult.TransportFailure)
            val model = DashboardViewModel(repo)
            model.load(DashboardReader.GUARDIAN, "s-1")
            advanceUntilIdle()

            assertIs<DashboardUiState.Failed>(model.state.value)
        }

    @Test
    fun `a slower earlier response cannot overwrite a later selection`() =
        runTest(dispatcher) {
            val repo =
                FakeDashboardRepository(
                    respond = { range ->
                        if (range == DashboardRange.YEAR) delay(1_000)
                        AuthResult.Ok(dashboardDto(examAverage = if (range == DashboardRange.YEAR) 11 else 22))
                    },
                )
            val model = DashboardViewModel(repo)
            model.load(DashboardReader.TEACHER, "e-1", "Sadia", "Physics")
            advanceUntilIdle()

            model.selectRange(DashboardRange.YEAR)
            model.selectRange(DashboardRange.ALL)
            advanceUntilIdle()

            assertEquals(DashboardRange.ALL, loaded(model).range)
            assertEquals(22, loaded(model).examAveragePercent)
            assertFalse(loaded(model).refreshing)
        }
}
