package com.shikkhokplus.app.feature.guardian

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.PayablesDto
import com.shikkhokplus.app.core.network.PaymentLineDto
import com.shikkhokplus.app.core.network.PaymentMonthDto
import com.shikkhokplus.app.core.network.PaymentsDto
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

/** G1's loading, G2's batches and G3's history, as plain JVM tests. */
@OptIn(ExperimentalCoroutinesApi::class)
class GuardianFlowsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake(
        var home: AuthResult<GuardianHomeDto> =
            AuthResult.Ok(GuardianHomeDto(listOf(childDto("Tasnim"), childDto("Ayan")))),
        var history: AuthResult<PaymentsDto> =
            AuthResult.Ok(
                PaymentsDto(
                    "Tasnim",
                    2026,
                    Money.of("2700.00"),
                    listOf(
                        PaymentMonthDto(
                            "2026-10",
                            listOf(
                                PaymentLineDto(
                                    "seat-Tasnim",
                                    "Maths",
                                    Money.of("1500.00"),
                                    "verifying",
                                    "2026-10-20",
                                    "2026-10-15",
                                    null,
                                    "Nagad",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
    ) : GuardianRepository, PaymentsRepository {
        override suspend fun home() = home

        override suspend fun me() = AuthResult.Ok(MeDto(phone = "+8801819552041"))

        override suspend fun payments(seat: String) = history

        override suspend fun payables(seat: String): AuthResult<PayablesDto> = AuthResult.Ok(PayablesDto())
    }

    @Test
    fun `the home keeps the shown child across a reload, and empty asks for the number`() = runTest(dispatcher) {
        val fake = Fake()
        val model = GuardianViewModel(fake)
        model.load()
        advanceUntilIdle()
        model.select(1)
        model.load()
        advanceUntilIdle()

        assertEquals("Ayan", (model.state.value as GuardianUiState.Loaded).child.name)

        fake.home = AuthResult.Ok(GuardianHomeDto())
        model.load()
        advanceUntilIdle()
        assertEquals(GuardianUiState.Empty("+8801819552041"), model.state.value)
    }

    @Test
    fun `the payment history keeps the server's months and states`() = runTest(dispatcher) {
        val model = PaymentsViewModel(Fake())

        model.load("seat-Tasnim")
        advanceUntilIdle()

        val loaded = assertIs<PaymentsUiState.Loaded>(model.state.value)
        assertEquals(Money.of("2700.00"), loaded.paidThisYear)
        assertEquals(LineState.VERIFYING, loaded.months.single().lines.single().state)
        assertEquals(null, loaded.next)
    }

    @Test
    fun `an unknown payment state fails rather than reading as owed`() {
        val dto =
            PaymentsDto(
                "Tasnim",
                2026,
                Money.of("0.00"),
                listOf(
                    PaymentMonthDto(
                        "2026-10",
                        listOf(PaymentLineDto("s", "Maths", Money.of("1.00"), "refunded", "2026-10-20")),
                    ),
                ),
            )

        assertIs<PaymentsUiState.Failed>(PaymentsMapper.afterLoad(dto, null))
    }

    @Test
    fun `a failed history read is retryable when offline`() = runTest(dispatcher) {
        val model = PaymentsViewModel(Fake(history = AuthResult.TransportFailure))

        model.load("seat-Tasnim")
        advanceUntilIdle()

        assertEquals(PaymentsUiState.Failed(GuardianStateMapper.OFFLINE_KEY, true), model.state.value)
    }
}
