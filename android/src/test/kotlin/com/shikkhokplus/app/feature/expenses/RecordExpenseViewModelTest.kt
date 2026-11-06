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
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** Recording an expense: format-only checks, the draft sent, the retry key. */
@OptIn(ExperimentalCoroutinesApi::class)
class RecordExpenseViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun model(repo: FakeExpensesRepository) =
        RecordExpenseViewModel(repo, today = "2026-11-06", mutationId = "key-1")

    @Test
    fun `the form opens on today with printing chosen and cannot be sent empty`() {
        val form = model(FakeExpensesRepository()).state.value
        assertEquals("2026-11-06", form.spentOn)
        assertEquals(ExpenseCategory.PRINTING, form.category)
        assertFalse(form.canSave)
    }

    @Test
    fun `it can be sent once there is a description and an amount that parses`() {
        val model = model(FakeExpensesRepository())
        model.what("Question papers")
        assertFalse(model.state.value.canSave)
        model.amount("12.345")
        assertFalse(model.state.value.canSave, "three decimals is not an amount")
        model.amount("৪৫০")
        assertTrue(model.state.value.canSave, "Bangla digits are an amount")
    }

    @Test
    fun `a blank description cannot be sent`() {
        val model = model(FakeExpensesRepository())
        model.what("   ")
        model.amount("450")
        assertFalse(model.state.value.canSave)
    }

    @Test
    fun `zero is left for the server to refuse in the person's language`() = runTest {
        val repo = FakeExpensesRepository()
        repo.recordResult = FakeExpensesRepository.refusal("expenses.amount_not_positive")
        val model = model(repo)
        model.what("Chalk")
        model.amount("0")
        assertTrue(model.state.value.canSave)

        model.save()
        advanceUntilIdle()

        assertEquals("expenses.amount_not_positive", model.state.value.failureKey)
        assertFalse(model.state.value.saved)
    }

    @Test
    fun `saving sends the trimmed draft under the form's retry key`() = runTest {
        val repo = FakeExpensesRepository()
        val model = model(repo)
        model.category(ExpenseCategory.RENT)
        model.what("  November rent ")
        model.amount("৳4,000")
        model.spentOn("2026-11-01")
        model.payee("  ")
        model.note(" Receipt 17 ")

        model.save()
        advanceUntilIdle()

        val sent = repo.recorded.single()
        assertEquals(ExpenseCategory.RENT, sent.category)
        assertEquals("November rent", sent.what)
        assertEquals(Money.of("4000.00"), sent.amount)
        assertEquals("2026-11-01", sent.spentOn)
        assertNull(sent.payee)
        assertEquals("Receipt 17", sent.note)
        assertEquals("key-1", sent.clientMutationId)
        assertTrue(model.state.value.saved)
    }

    @Test
    fun `a resend after a failure reuses the same retry key`() = runTest {
        val repo = FakeExpensesRepository()
        repo.recordResult = AuthResult.TransportFailure
        val model = model(repo)
        model.what("Chalk")
        model.amount("120")

        model.save()
        advanceUntilIdle()
        assertEquals("error.network.unreachable", model.state.value.failureKey)
        assertFalse(model.state.value.saving)

        repo.recordResult = AuthResult.Ok(FakeExpensesRepository.expense())
        model.save()
        advanceUntilIdle()

        assertEquals(listOf("key-1", "key-1"), repo.recorded.map { it.clientMutationId })
        assertTrue(model.state.value.saved)
    }

    @Test
    fun `editing a field clears the last refusal`() = runTest {
        val repo = FakeExpensesRepository()
        repo.recordResult = FakeExpensesRepository.refusal("expenses.date_in_future")
        val model = model(repo)
        model.what("Chalk")
        model.amount("120")
        model.save()
        advanceUntilIdle()
        assertEquals("expenses.date_in_future", model.state.value.failureKey)

        model.spentOn("2026-11-05")
        assertNull(model.state.value.failureKey)
    }

    @Test
    fun `a form that cannot be sent sends nothing`() = runTest {
        val repo = FakeExpensesRepository()
        model(repo).save()
        advanceUntilIdle()
        assertTrue(repo.recorded.isEmpty())
    }

    @Test
    fun `long text is cut to what the server stores`() {
        val model = model(FakeExpensesRepository())
        model.what("x".repeat(500))
        model.payee("y".repeat(500))
        model.note("z".repeat(500))
        assertEquals(120, model.state.value.what.length)
        assertEquals(80, model.state.value.payee.length)
        assertEquals(200, model.state.value.note.length)
    }
}
