package com.shikkhokplus.app.feature.fees

import com.shikkhokplus.app.core.network.SeatExtraFeesDto
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.FeeCycleDto
import com.shikkhokplus.app.core.network.FeeHistoryDto
import com.shikkhokplus.app.core.network.PaymentReviewDto
import com.shikkhokplus.app.core.network.RecordPaymentBodyDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.verify.review
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
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * "Record payment" on the teacher's fee history: the ViewModel's state
 * machine for the sheet, per team practice (loading, success, error, and
 * the explicit retry of a failed write [TC-8, D-9]).
 *
 * The money is the server's. These assert only what the client sends
 * and what it shows: the sheet opens at the server's total, carry or
 * waive is asked exactly when the typed amount is short, a success
 * re-reads the history, and a failure keeps the sheet AND its retry key,
 * so the teacher's second tap is a replay the server can recognise.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class RecordPaymentViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun history(total: String = "1500.00") =
        FeeHistoryDto(
            cycles =
                listOf(
                    FeeCycleDto(
                        period = "2026-10",
                        dueDate = "2026-10-10",
                        charged = Money.of("1500.00"),
                        outstanding = Money.of(total),
                        status = "unpaid",
                    ),
                ),
            totalOutstanding = Money.of(total),
        )

    private class Reads(var history: FeeHistoryDto) : FeesRepository {
        var teacherReads = 0

        override suspend fun myFees(enrollmentId: String): AuthResult<FeeHistoryDto> = AuthResult.Ok(history)

        override suspend fun childFees(enrollmentId: String): AuthResult<FeeHistoryDto> = AuthResult.Ok(history)

        override suspend fun enrollmentFees(enrollmentId: String): AuthResult<FeeHistoryDto> {
            teacherReads++
            return AuthResult.Ok(history)
        }

        override suspend fun seatExtraFees(enrollmentId: String): AuthResult<SeatExtraFeesDto> =
            AuthResult.Ok(SeatExtraFeesDto())
    }

    private class Writes(
        val replies: ArrayDeque<AuthResult<PaymentReviewDto>>,
    ) : RecordPaymentRepository {
        val sent = mutableListOf<Pair<String, RecordPaymentBodyDto>>()

        override suspend fun recordPayment(
            enrollmentId: String,
            body: RecordPaymentBodyDto,
        ): AuthResult<PaymentReviewDto> {
            sent += enrollmentId to body
            return replies.removeFirst()
        }
    }

    private fun writer(vararg replies: AuthResult<PaymentReviewDto>) = Writes(ArrayDeque(replies.toList()))

    private fun refused(code: String, key: String): AuthResult<PaymentReviewDto> =
        AuthResult.Refused(ErrorEnvelope(ErrorBody(code = code, messageKey = key, retryable = false)))

    private fun model(
        reads: Reads,
        writes: Writes?,
    ): FeesViewModel {
        var n = 0
        return FeesViewModel(reads, recorder = writes, newMutationId = { "key-${++n}" })
    }

    @Test
    fun `a family reader is built without the write and cannot open the sheet`() =
        runTest(dispatcher) {
            val vm = model(Reads(history()), writes = null)
            vm.load("e-1", FeeReader.GUARDIAN)
            advanceUntilIdle()

            assertFalse(vm.canRecord)
            vm.openRecord()
            assertNull(vm.sheet.value)
        }

    @Test
    fun `the sheet opens at the server's total, in cash, with no choice made`() =
        runTest(dispatcher) {
            val vm = model(Reads(history("1500.00")), writer())
            vm.load("e-1", FeeReader.TEACHER)
            advanceUntilIdle()

            vm.openRecord()

            val sheet = assertNotNull(vm.sheet.value)
            assertEquals("1500", sheet.typed)
            assertEquals(RecordSheet.CASH, sheet.channel)
            assertEquals(RecordSide.EXACT, sheet.side)
            assertNull(sheet.disposition)
            assertEquals("key-1", sheet.clientMutationId)
        }

    @Test
    fun `the full amount is recorded with no disposition, then the history is read again`() =
        runTest(dispatcher) {
            val reads = Reads(history())
            val writes = writer(AuthResult.Ok(review()))
            val vm = model(reads, writes)
            vm.load("e-1", FeeReader.TEACHER)
            advanceUntilIdle()

            vm.openRecord()
            vm.typeRecordNote("Paid at the door")
            vm.confirmRecord()
            advanceUntilIdle()

            assertEquals(
                listOf(
                    "e-1" to
                        RecordPaymentBodyDto(
                            amount = Money.of("1500.00"),
                            channel = "cash",
                            note = "Paid at the door",
                            clientMutationId = "key-1",
                        ),
                ),
                writes.sent,
            )
            assertNull(vm.sheet.value)
            assertTrue(vm.recorded.value)
            assertEquals(2, reads.teacherReads, "a success re-reads what the server recorded")
        }

    @Test
    fun `a short amount asks carry or waive and sends nothing until one is chosen`() =
        runTest(dispatcher) {
            val writes = writer(AuthResult.Ok(review()))
            val vm = model(Reads(history()), writes)
            vm.load("e-1", FeeReader.TEACHER)
            advanceUntilIdle()
            vm.openRecord()

            vm.typeRecordAmount("1000")
            assertTrue(assertNotNull(vm.sheet.value).needsDisposition)
            vm.confirmRecord()
            advanceUntilIdle()
            assertEquals(emptyList(), writes.sent, "no disposition, no send")

            vm.chooseRecordDisposition("waived")
            vm.confirmRecord()
            advanceUntilIdle()

            val body = writes.sent.single().second
            assertEquals(Money.of("1000.00"), body.amount)
            assertEquals("waived", body.shortfallDisposition)
        }

    @Test
    fun `changing the amount to one that is not short drops the choice`() =
        runTest(dispatcher) {
            val vm = model(Reads(history()), writer())
            vm.load("e-1", FeeReader.TEACHER)
            advanceUntilIdle()
            vm.openRecord()

            vm.typeRecordAmount("900")
            vm.chooseRecordDisposition("carried")
            vm.typeRecordAmount("800")
            assertEquals("carried", vm.sheet.value?.disposition, "still short, still carried")

            vm.typeRecordAmount("2000")
            assertEquals(RecordSide.OVER, vm.sheet.value?.side)
            assertNull(vm.sheet.value?.disposition)
        }

    @Test
    fun `a mobile service is sent by name with its reference`() =
        runTest(dispatcher) {
            val writes = writer(AuthResult.Ok(review()))
            val vm = model(Reads(history()), writes)
            vm.load("e-1", FeeReader.TEACHER)
            advanceUntilIdle()
            vm.openRecord()

            vm.chooseRecordChannel("cheque")
            assertEquals(RecordSheet.CASH, vm.sheet.value?.channel, "not a channel the server offers")
            vm.chooseRecordChannel("bKash")
            vm.typeRecordReference(" 9KD7Q2XL1M ")
            vm.confirmRecord()
            advanceUntilIdle()

            val body = writes.sent.single().second
            assertEquals("bKash", body.channel)
            assertEquals("9KD7Q2XL1M", body.reference)
        }

    @Test
    fun `a refusal keeps the sheet with the server's message, and the retry reuses the key`() =
        runTest(dispatcher) {
            val writes =
                writer(
                    refused("SHORTFALL_DISPOSITION_REQUIRED", "fees.verification.disposition_required"),
                    AuthResult.Ok(review()),
                )
            val vm = model(Reads(history()), writes)
            vm.load("e-1", FeeReader.TEACHER)
            advanceUntilIdle()
            vm.openRecord()

            vm.confirmRecord()
            advanceUntilIdle()

            val kept = assertNotNull(vm.sheet.value)
            assertEquals("fees.verification.disposition_required", kept.errorKey)
            assertFalse(kept.busy)
            assertFalse(vm.recorded.value)

            vm.confirmRecord()
            advanceUntilIdle()

            assertEquals(listOf("key-1", "key-1"), writes.sent.map { it.second.clientMutationId })
            assertNull(vm.sheet.value)
        }

    @Test
    fun `a lost connection keeps the sheet, offline, and nothing is queued`() =
        runTest(dispatcher) {
            val writes = writer(AuthResult.TransportFailure)
            val vm = model(Reads(history()), writes)
            vm.load("e-1", FeeReader.TEACHER)
            advanceUntilIdle()
            vm.openRecord()

            vm.confirmRecord()
            advanceUntilIdle()

            assertEquals(FeeStateMapper.OFFLINE_KEY, vm.sheet.value?.errorKey)
            assertEquals(1, writes.sent.size, "V1 has no local write queue [TC-8]")
        }

    @Test
    fun `nothing owed opens blank, and dismissing records nothing`() =
        runTest(dispatcher) {
            val reads = Reads(FeeHistoryDto(cycles = emptyList(), totalOutstanding = Money.ZERO))
            val writes = writer()
            val vm = model(reads, writes)
            vm.load("e-1", FeeReader.TEACHER)
            advanceUntilIdle()
            assertIs<FeeUiState.Empty>(vm.state.value)

            vm.openRecord()
            assertEquals("", vm.sheet.value?.typed)
            assertEquals(RecordSide.INVALID, vm.sheet.value?.side)
            vm.dismissRecord()

            assertNull(vm.sheet.value)
            assertEquals(emptyList(), writes.sent)
        }
}
