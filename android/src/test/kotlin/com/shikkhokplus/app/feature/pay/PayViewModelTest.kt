package com.shikkhokplus.app.feature.pay

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ClaimDto
import com.shikkhokplus.app.core.network.ClaimSubmitDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.PayableDto
import com.shikkhokplus.app.core.network.PayablesDto
import com.shikkhokplus.app.core.network.PaymentDestinationDto
import com.shikkhokplus.app.core.network.WaitingPaymentDto
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
 * S3's flow: choose, fill in, send, sent -- and that a failed send keeps
 * what was typed rather than queueing it.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PayViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun payable(seat: String, batch: String) =
        PayableDto(seat, batch, "2026-10", Money.of("1500.00"), "2026-10-20")

    private class Fake(
        var payables: AuthResult<PayablesDto>,
        var destination: AuthResult<PaymentDestinationDto?> =
            AuthResult.Ok(PaymentDestinationDto("01712345678", "bKash", listOf("bKash", "Nagad", "Rocket"), "Najma")),
        var submitted: AuthResult<ClaimDto> =
            AuthResult.Ok(
                ClaimDto(
                    "c-1",
                    "2026-10",
                    Money.of("1500.00"),
                    status = "pending",
                    channel = "bKash",
                    submittedAt = "2026-10-17T09:22:00Z",
                ),
            ),
    ) : PayRepository {
        val sent = mutableListOf<Pair<String, ClaimSubmitDto>>()

        override suspend fun payables() = payables

        override suspend fun destination(enrollmentId: String) = destination

        override suspend fun submit(enrollmentId: String, claim: ClaimSubmitDto): AuthResult<ClaimDto> {
            sent += enrollmentId to claim
            return submitted
        }
    }

    @Test
    fun `one fee and nothing waiting opens the form with the amount and service filled`() = runTest(dispatcher) {
        val model = PayViewModel(Fake(AuthResult.Ok(PayablesDto(listOf(payable("e-1", "Maths"))))))

        model.load()
        advanceUntilIdle()

        val filling = assertIs<PayUiState.Filling>(model.state.value)
        assertEquals("1500.00", filling.form.amount)
        assertEquals("bKash", filling.form.channel)
        assertEquals("Najma", filling.destination?.teacherName)
        assertEquals(false, filling.canChange)
    }

    @Test
    fun `several fees, or a waiting one, ask which to pay`() = runTest(dispatcher) {
        val model =
            PayViewModel(
                Fake(
                    AuthResult.Ok(
                        PayablesDto(listOf(payable("e-1", "Maths")), listOf(WaitingPaymentDto("Chemistry", "2026-10"))),
                    ),
                ),
            )

        model.load()
        advanceUntilIdle()
        val choosing = assertIs<PayUiState.Choosing>(model.state.value)
        model.choose(choosing.options.single())
        advanceUntilIdle()
        val filling = assertIs<PayUiState.Filling>(model.state.value)
        model.change()

        assertEquals(listOf(WaitingLine("Chemistry", "2026-10")), choosing.waiting)
        assertEquals(true, filling.canChange)
        assertEquals(choosing, model.state.value)
    }

    @Test
    fun `a seat named on the way in opens straight away`() = runTest(dispatcher) {
        val model =
            PayViewModel(Fake(AuthResult.Ok(PayablesDto(listOf(payable("e-1", "Maths"), payable("e-2", "Physics"))))))

        model.load(preselect = "e-2")
        advanceUntilIdle()

        assertEquals("e-2", assertIs<PayUiState.Filling>(model.state.value).option.enrollmentId)
    }

    @Test
    fun `a short ID is flagged and nothing is sent`() = runTest(dispatcher) {
        val fake = Fake(AuthResult.Ok(PayablesDto(listOf(payable("e-1", "Maths")))))
        val model = PayViewModel(fake)
        model.load()
        advanceUntilIdle()
        val form = assertIs<PayUiState.Filling>(model.state.value).form

        model.type(form.copy(transactionId = "DJ6"))
        model.send()
        advanceUntilIdle()

        assertEquals(FormProblem.TRANSACTION_ID_SHORT, assertIs<PayUiState.Filling>(model.state.value).problem)
        assertEquals(emptyList(), fake.sent)
    }

    @Test
    fun `a sent payment carries what was claimed and the ID`() = runTest(dispatcher) {
        val fake = Fake(AuthResult.Ok(PayablesDto(listOf(payable("e-1", "Maths")))))
        val model = PayViewModel(fake)
        model.load()
        advanceUntilIdle()
        val form = assertIs<PayUiState.Filling>(model.state.value).form

        model.type(form.copy(transactionId = "DJ62K0LQ7V"))
        model.send()
        advanceUntilIdle()

        assertEquals(listOf("e-1" to ClaimSubmitDto(Money.of("1500.00"), "bKash", "DJ62K0LQ7V")), fake.sent)
        val sent = assertIs<PayUiState.Sent>(model.state.value)
        assertEquals("DJ62K0LQ7V", sent.payment.transactionId)
        assertEquals("Najma", sent.teacherName)
    }

    @Test
    fun `no connection keeps the details and is not queued`() = runTest(dispatcher) {
        val fake =
            Fake(AuthResult.Ok(PayablesDto(listOf(payable("e-1", "Maths")))), submitted = AuthResult.TransportFailure)
        val model = PayViewModel(fake)
        model.load()
        advanceUntilIdle()
        val form = assertIs<PayUiState.Filling>(model.state.value).form.copy(transactionId = "DJ62K0LQ7V")
        model.type(form)

        model.send()
        advanceUntilIdle()

        val failed = assertIs<PayUiState.Filling>(model.state.value)
        assertEquals(PayMapper.OFFLINE_KEY, failed.failedKey)
        assertEquals(form, failed.form)
        assertEquals(false, failed.sending)
    }

    @Test
    fun `a refusal carries the server's key`() = runTest(dispatcher) {
        val refused = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, "fees.claim.no_open_cycle")))
        val fake = Fake(AuthResult.Ok(PayablesDto(listOf(payable("e-1", "Maths")))), submitted = refused)
        val model = PayViewModel(fake)
        model.load()
        advanceUntilIdle()
        model.type(assertIs<PayUiState.Filling>(model.state.value).form.copy(transactionId = "DJ62K0LQ7V"))

        model.send()
        advanceUntilIdle()

        assertEquals("fees.claim.no_open_cycle", assertIs<PayUiState.Filling>(model.state.value).failedKey)
    }

    @Test
    fun `no number set leaves the destination out, and a failed read can be retried`() = runTest(dispatcher) {
        val fake = Fake(AuthResult.Ok(PayablesDto(listOf(payable("e-1", "Maths")))), destination = AuthResult.Ok(null))
        val model = PayViewModel(fake)
        model.load()
        advanceUntilIdle()
        val filling = assertIs<PayUiState.Filling>(model.state.value)

        fake.payables = AuthResult.TransportFailure
        model.load()
        advanceUntilIdle()

        assertEquals(null, filling.destination)
        assertEquals(listOf("bKash", "Nagad", "Rocket"), filling.channels)
        assertEquals(PayUiState.Failed(PayMapper.OFFLINE_KEY, true), model.state.value)
    }

    @Test
    fun `nothing to pay is the empty choice`() = runTest(dispatcher) {
        val model = PayViewModel(Fake(AuthResult.Ok(PayablesDto())))

        model.load()
        advanceUntilIdle()

        assertEquals(PayUiState.Choosing(emptyList(), emptyList()), model.state.value)
    }
}
