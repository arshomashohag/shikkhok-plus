package com.shikkhokplus.app.feature.paymentmethods

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

/** P1: the teacher's list of payment methods. */
@OptIn(ExperimentalCoroutinesApi::class)
class PaymentMethodsViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    @Test
    fun `loading becomes loaded with each method as a row`() = runTest {
        val repo = FakePaymentMethodsRepository()
        repo.listResults =
            mutableListOf(
                AuthResult.Ok(
                    listOf(
                        FakePaymentMethodsRepository.mobileMethod(),
                        FakePaymentMethodsRepository.bankMethod(),
                    ),
                ),
            )
        val model = PaymentMethodsViewModel(repo)

        assertEquals(PaymentMethodsUiState.Loading, model.state.value)
        model.load()
        advanceUntilIdle()
        val loaded = assertIs<PaymentMethodsUiState.Loaded>(model.state.value)
        assertEquals(listOf("bKash", "Dutch-Bangla Bank"), loaded.rows.map { it.title })
        assertEquals("01712345678", loaded.rows[0].detail)
        assertEquals("Rahima Akter · ••• 4521", loaded.rows[1].detail)
        assertEquals("Mirpur branch", loaded.rows[1].extra)
        assertEquals("Use Send Money, not Cash Out", loaded.rows[0].note)
    }

    @Test
    fun `no methods is the empty state`() = runTest {
        val model = PaymentMethodsViewModel(FakePaymentMethodsRepository())
        model.load()
        advanceUntilIdle()
        assertEquals(PaymentMethodsUiState.Empty, model.state.value)
    }

    @Test
    fun `error then retry reads again and loads`() = runTest {
        val repo = FakePaymentMethodsRepository()
        repo.listResults =
            mutableListOf(
                AuthResult.TransportFailure,
                AuthResult.Ok(listOf(FakePaymentMethodsRepository.mobileMethod())),
            )
        val model = PaymentMethodsViewModel(repo)
        model.load()
        advanceUntilIdle()
        val failed = assertIs<PaymentMethodsUiState.Failed>(model.state.value)
        assertTrue(failed.retryable)

        model.retry()
        advanceUntilIdle()

        assertIs<PaymentMethodsUiState.Loaded>(model.state.value)
        assertEquals(2, repo.lists)
    }

    @Test
    fun `retiring a method reloads the list`() = runTest {
        val repo = FakePaymentMethodsRepository()
        repo.listResults =
            mutableListOf(
                AuthResult.Ok(listOf(FakePaymentMethodsRepository.mobileMethod())),
                AuthResult.Ok(emptyList()),
            )
        val model = PaymentMethodsViewModel(repo)
        model.load()
        advanceUntilIdle()

        model.retire("m1")
        advanceUntilIdle()

        assertEquals(listOf("m1"), repo.retired)
        assertEquals(PaymentMethodsUiState.Empty, model.state.value)
    }

    @Test
    fun `a failed retire keeps the list and says why`() = runTest {
        val repo = FakePaymentMethodsRepository()
        repo.listResults =
            mutableListOf(AuthResult.Ok(listOf(FakePaymentMethodsRepository.mobileMethod())))
        repo.retireResult = AuthResult.TransportFailure
        val model = PaymentMethodsViewModel(repo)
        model.load()
        advanceUntilIdle()

        model.retire("m1")
        advanceUntilIdle()

        val loaded = assertIs<PaymentMethodsUiState.Loaded>(model.state.value)
        assertEquals(1, loaded.rows.size)
        assertEquals("error.network.unreachable", loaded.removeFailedKey)
    }

    @Test
    fun `a loaded method can be found by id for editing`() = runTest {
        val repo = FakePaymentMethodsRepository()
        repo.listResults =
            mutableListOf(AuthResult.Ok(listOf(FakePaymentMethodsRepository.bankMethod())))
        val model = PaymentMethodsViewModel(repo)
        model.load()
        advanceUntilIdle()

        assertEquals("Mirpur branch", model.methodFor("b1")?.branchName)
        assertEquals(null, model.methodFor("missing"))
    }
}
