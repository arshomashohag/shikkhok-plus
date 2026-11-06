package com.shikkhokplus.app.feature.expenses

import com.shikkhokplus.app.core.model.Money
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

/** The expense list and the monthly summary: their state machines. */
@OptIn(ExperimentalCoroutinesApi::class)
class ExpensesViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun listModel(repo: FakeExpensesRepository) = ExpensesViewModel(repo, thisMonth = { "2026-11" })

    @Test
    fun `a month with expenses shows the server's total, rows and categories`() = runTest {
        val repo = FakeExpensesRepository()
        repo.monthResults =
            mutableListOf(AuthResult.Ok(FakeExpensesRepository.month(FakeExpensesRepository.expense())))
        val model = listModel(repo)

        assertEquals(ExpensesBody.Loading, model.state.value.body)
        model.load()
        advanceUntilIdle()

        val loaded = assertIs<ExpensesBody.Loaded>(model.state.value.body)
        assertEquals(Money.of("450.00"), loaded.total)
        assertEquals(listOf("Question papers"), loaded.rows.map { it.what })
        assertEquals(ExpenseCategory.PRINTING, loaded.rows.single().category)
        assertEquals("Nilkhet Press", loaded.rows.single().payee)
        assertEquals(listOf(CategoryTotal(ExpenseCategory.PRINTING, Money.of("450.00"))), loaded.byCategory)
        assertEquals(listOf("2026-11"), repo.monthsRead)
    }

    @Test
    fun `a voided expense stays listed with its reason`() = runTest {
        val repo = FakeExpensesRepository()
        repo.monthResults =
            mutableListOf(AuthResult.Ok(FakeExpensesRepository.month(FakeExpensesRepository.expense(voided = true))))
        val model = listModel(repo)
        model.load()
        advanceUntilIdle()

        val row = assertIs<ExpensesBody.Loaded>(model.state.value.body).rows.single()
        assertTrue(row.voided)
        assertEquals("Typed twice", row.voidReason)
    }

    @Test
    fun `an empty month is the empty state`() = runTest {
        val model = listModel(FakeExpensesRepository())
        model.load()
        advanceUntilIdle()
        assertEquals(ExpensesBody.Empty, model.state.value.body)
    }

    @Test
    fun `an unknown category reads as other rather than failing`() = runTest {
        val repo = FakeExpensesRepository()
        repo.monthResults =
            mutableListOf(
                AuthResult.Ok(FakeExpensesRepository.month(FakeExpensesRepository.expense(category = "insurance"))),
            )
        val model = listModel(repo)
        model.load()
        advanceUntilIdle()
        assertEquals(
            ExpenseCategory.OTHER,
            assertIs<ExpensesBody.Loaded>(model.state.value.body).rows.single().category,
        )
    }

    @Test
    fun `offline then retry reads again and loads`() = runTest {
        val repo = FakeExpensesRepository()
        repo.monthResults =
            mutableListOf(
                AuthResult.TransportFailure,
                AuthResult.Ok(FakeExpensesRepository.month(FakeExpensesRepository.expense())),
            )
        val model = listModel(repo)
        model.load()
        advanceUntilIdle()
        val failed = assertIs<ExpensesBody.Failed>(model.state.value.body)
        assertEquals("error.network.unreachable", failed.messageKey)
        assertTrue(failed.retryable)

        model.retry()
        advanceUntilIdle()
        assertIs<ExpensesBody.Loaded>(model.state.value.body)
        assertEquals(2, repo.monthsRead.size)
    }

    @Test
    fun `a refusal carries the server's key and retryable flag`() = runTest {
        val repo = FakeExpensesRepository()
        repo.monthResults = mutableListOf(FakeExpensesRepository.refusal("error.unexpected", retryable = false))
        val model = listModel(repo)
        model.load()
        advanceUntilIdle()
        assertEquals(ExpensesBody.Failed("error.unexpected", retryable = false), model.state.value.body)
    }

    @Test
    fun `stepping back reads the earlier month and allows stepping forward again`() = runTest {
        val repo = FakeExpensesRepository()
        val model = listModel(repo)
        model.load()
        advanceUntilIdle()
        assertFalse(model.state.value.canGoForward)

        model.shift(-1)
        advanceUntilIdle()

        assertEquals("2026-10", model.state.value.month)
        assertTrue(model.state.value.canGoForward)
        assertEquals(listOf("2026-11", "2026-10"), repo.monthsRead)
    }

    @Test
    fun `a year boundary steps from January to December`() = runTest {
        val repo = FakeExpensesRepository()
        val model = ExpensesViewModel(repo, thisMonth = { "2027-01" })
        model.shift(-1)
        advanceUntilIdle()
        assertEquals("2026-12", model.state.value.month)
    }

    @Test
    fun `there is no stepping past the current month`() = runTest {
        val repo = FakeExpensesRepository()
        val model = listModel(repo)
        model.load()
        advanceUntilIdle()

        model.shift(1)
        advanceUntilIdle()

        assertEquals("2026-11", model.state.value.month)
        assertEquals(listOf("2026-11"), repo.monthsRead)
    }

    @Test
    fun `voiding sends the trimmed reason and reloads the month`() = runTest {
        val repo = FakeExpensesRepository()
        repo.monthResults =
            mutableListOf(
                AuthResult.Ok(FakeExpensesRepository.month(FakeExpensesRepository.expense())),
                AuthResult.Ok(FakeExpensesRepository.month(FakeExpensesRepository.expense(voided = true))),
            )
        val model = listModel(repo)
        model.load()
        advanceUntilIdle()

        model.void("x1", "  Typed twice  ")
        advanceUntilIdle()

        assertEquals(listOf<Pair<String, String?>>("x1" to "Typed twice"), repo.voided)
        assertTrue(assertIs<ExpensesBody.Loaded>(model.state.value.body).rows.single().voided)
        assertNull(model.state.value.voidFailedKey)
    }

    @Test
    fun `a blank reason is sent as none`() = runTest {
        val repo = FakeExpensesRepository()
        val model = listModel(repo)
        model.void("x1", "   ")
        advanceUntilIdle()
        assertEquals(listOf<Pair<String, String?>>("x1" to null), repo.voided)
    }

    @Test
    fun `a refused void keeps the list and says why`() = runTest {
        val repo = FakeExpensesRepository()
        repo.monthResults =
            mutableListOf(AuthResult.Ok(FakeExpensesRepository.month(FakeExpensesRepository.expense())))
        repo.voidResult = FakeExpensesRepository.refusal("expenses.already_voided")
        val model = listModel(repo)
        model.load()
        advanceUntilIdle()

        model.void("x1", "")
        advanceUntilIdle()

        assertEquals("expenses.already_voided", model.state.value.voidFailedKey)
        assertFalse(assertIs<ExpensesBody.Loaded>(model.state.value.body).rows.single().voided)
        assertEquals(1, repo.monthsRead.size)
    }

    @Test
    fun `an offline void says so`() = runTest {
        val repo = FakeExpensesRepository()
        repo.voidResult = AuthResult.TransportFailure
        val model = listModel(repo)
        model.void("x1", "")
        advanceUntilIdle()
        assertEquals("error.network.unreachable", model.state.value.voidFailedKey)
    }

    @Test
    fun `the summary carries the server's figures and verdict unchanged`() = runTest {
        val repo = FakeExpensesRepository()
        val model = SummaryViewModel(repo, thisMonth = { "2026-11" })
        model.load()
        advanceUntilIdle()

        val summary = assertIs<SummaryBody.Loaded>(model.state.value.body).summary
        assertEquals(Money.of("3500.00"), summary.collectedTotal)
        assertEquals(Money.of("4000.00"), summary.spentTotal)
        // The verdict is read, never derived: the client compares nothing.
        assertEquals(NetKind.DEFICIT, summary.netKind)
        assertEquals(Money.of("500.00"), summary.net)
        assertEquals(Money.of("1200.00"), summary.owedMonthly)
        assertEquals(listOf("Half-yearly exam"), summary.fees.map { it.label })
        assertEquals(listOf(CategoryTotal(ExpenseCategory.RENT, Money.of("4000.00"))), summary.spentByCategory)
    }

    @Test
    fun `each verdict reads as itself and an unknown one claims nothing`() {
        assertEquals(NetKind.SURPLUS, NetKind.fromWire("surplus"))
        assertEquals(NetKind.DEFICIT, NetKind.fromWire("deficit"))
        assertEquals(NetKind.EVEN, NetKind.fromWire("even"))
        assertEquals(NetKind.EVEN, NetKind.fromWire("windfall"))
    }

    @Test
    fun `the summary steps months and fails with a retry when offline`() = runTest {
        val repo = FakeExpensesRepository()
        repo.summaryResult = AuthResult.TransportFailure
        val model = SummaryViewModel(repo, thisMonth = { "2026-11" })
        model.shift(-1)
        advanceUntilIdle()

        assertEquals("2026-10", model.state.value.month)
        assertEquals(SummaryBody.Failed("error.network.unreachable", retryable = true), model.state.value.body)

        model.shift(1)
        model.shift(1)
        advanceUntilIdle()
        assertEquals("2026-11", model.state.value.month)
        assertEquals(listOf("2026-10", "2026-11"), repo.summariesRead)
    }
}
