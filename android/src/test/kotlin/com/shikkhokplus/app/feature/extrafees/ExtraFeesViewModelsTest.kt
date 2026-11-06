package com.shikkhokplus.app.feature.extrafees

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.BatchExtraFeesDto
import com.shikkhokplus.app.core.network.ChargeableStudentDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.ExamDto
import com.shikkhokplus.app.core.network.ExtraFeeDetailDto
import com.shikkhokplus.app.core.network.ExtraFeeRaiseRequestDto
import com.shikkhokplus.app.core.network.ExtraFeeStudentDto
import com.shikkhokplus.app.core.network.ExtraFeeSummaryDto
import com.shikkhokplus.app.core.network.PaymentReviewDto
import com.shikkhokplus.app.core.network.RecordPaymentBodyDto
import com.shikkhokplus.app.core.network.SeatAmountDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.fees.RecordPaymentRepository
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

/** A batch's exam and other fees: the list, raising one, and recording against one. */
@OptIn(ExperimentalCoroutinesApi::class)
class ExtraFeesViewModelsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake : ExtraFeesRepository {
        var batch: AuthResult<BatchExtraFeesDto> = AuthResult.Ok(BatchExtraFeesDto())
        var detail: AuthResult<ExtraFeeDetailDto> = AuthResult.Ok(detail())
        var raiseResult: AuthResult<ExtraFeeSummaryDto> = AuthResult.Ok(summary())
        var exams: AuthResult<List<ExamDto>> = AuthResult.Ok(emptyList())
        val raised = mutableListOf<Pair<String, ExtraFeeRaiseRequestDto>>()
        var batchReads = 0
        var detailReads = 0

        override suspend fun batchFees(batchId: String): AuthResult<BatchExtraFeesDto> {
            batchReads++
            return batch
        }

        override suspend fun fee(extraFeeId: String): AuthResult<ExtraFeeDetailDto> {
            detailReads++
            return detail
        }

        override suspend fun raise(batchId: String, request: ExtraFeeRaiseRequestDto): AuthResult<ExtraFeeSummaryDto> {
            raised += batchId to request
            return raiseResult
        }

        override suspend fun exams(batchId: String): AuthResult<List<ExamDto>> = exams
    }

    private class Recorder : RecordPaymentRepository {
        var reply: AuthResult<PaymentReviewDto> = AuthResult.Ok(review())
        val sent = mutableListOf<Pair<String, RecordPaymentBodyDto>>()

        override suspend fun recordPayment(
            enrollmentId: String,
            body: RecordPaymentBodyDto,
        ): AuthResult<PaymentReviewDto> {
            sent += enrollmentId to body
            return reply
        }
    }

    private fun refusal(key: String, retryable: Boolean = false) =
        AuthResult.Refused(ErrorEnvelope(ErrorBody("X", retryable, key)))

    private fun students() =
        BatchExtraFeesDto(
            chargeableStudents =
                listOf(
                    ChargeableStudentDto("e-1", "Tanvir"),
                    ChargeableStudentDto("e-2", "Tania"),
                    ChargeableStudentDto("e-3", "Rafi"),
                ),
        )

    private fun exam(id: String, cancelled: Boolean = false) =
        ExamDto(examId = id, title = "Mid-term $id", date = "2026-11-20", totalMarks = 50, cancelled = cancelled)

    // ------------------------------------------------------------- list

    @Test
    fun `the list shows the server's fees and an empty batch is empty`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.Ok(BatchExtraFeesDto(fees = listOf(summary())))
        val model = ExtraFeesViewModel(fake)
        model.load("b-1")
        advanceUntilIdle()
        assertEquals(listOf("f-1"), assertIs<ExtraFeesUiState.Loaded>(model.state.value).fees.map { it.extraFeeId })

        fake.batch = AuthResult.Ok(BatchExtraFeesDto())
        model.load("b-1")
        advanceUntilIdle()
        assertTrue(assertIs<ExtraFeesUiState.Loaded>(model.state.value).fees.isEmpty())
    }

    @Test
    fun `an offline list read can be retried`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.TransportFailure
        val model = ExtraFeesViewModel(fake)
        model.load("b-1")
        advanceUntilIdle()
        assertEquals(ExtraFeesUiState.Failed("error.network.unreachable", true), model.state.value)

        fake.batch = AuthResult.Ok(BatchExtraFeesDto())
        model.retry()
        advanceUntilIdle()
        assertIs<ExtraFeesUiState.Loaded>(model.state.value)
        assertEquals(2, fake.batchReads)
    }

    // ------------------------------------------------------------ raise

    private fun raiseModel(fake: Fake) = RaiseFeeViewModel(fake, today = "2026-11-06", mutationId = "key-1")

    @Test
    fun `the form lists the server's students and the batch's live exams`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.Ok(students())
        fake.exams = AuthResult.Ok(listOf(exam("x-1"), exam("x-2", cancelled = true)))
        val model = raiseModel(fake)
        model.load("b-1")
        advanceUntilIdle()

        val form = model.state.value
        assertFalse(form.loading)
        assertEquals(listOf("Tanvir", "Tania", "Rafi"), form.students.map { it.name })
        assertEquals(listOf("x-1"), form.exams.map { it.examId })
        assertEquals(3, form.chargedCount)
        assertEquals("2026-11-06", form.dueOn)
    }

    @Test
    fun `failing to read the exams still lets a fee be raised`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.Ok(students())
        fake.exams = AuthResult.TransportFailure
        val model = raiseModel(fake)
        model.load("b-1")
        advanceUntilIdle()

        assertTrue(model.state.value.exams.isEmpty())
        assertNull(model.state.value.loadFailedKey)
    }

    @Test
    fun `failing to read the students says why and can be retried`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = refusal("error.unexpected")
        val model = raiseModel(fake)
        model.load("b-1")
        advanceUntilIdle()
        assertEquals("error.unexpected", model.state.value.loadFailedKey)

        fake.batch = AuthResult.Ok(students())
        model.retry()
        advanceUntilIdle()
        assertNull(model.state.value.loadFailedKey)
        assertEquals(3, model.state.value.students.size)
    }

    @Test
    fun `the form can be sent once named, priced and reaching someone`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.Ok(students())
        val model = raiseModel(fake)
        model.load("b-1")
        advanceUntilIdle()
        assertFalse(model.state.value.canRaise)

        model.label("Half-yearly exam")
        assertFalse(model.state.value.canRaise)
        model.amount("৫০০")
        assertTrue(model.state.value.canRaise)

        listOf("e-1", "e-2", "e-3").forEach { model.choose(it, SeatChoice.LEAVE_OUT) }
        assertEquals(0, model.state.value.chargedCount)
        assertFalse(model.state.value.canRaise, "a fee that reaches nobody cannot be sent")
    }

    @Test
    fun `waived students are charged zero and left-out students are excluded`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.Ok(students())
        fake.exams = AuthResult.Ok(listOf(exam("x-1")))
        val model = raiseModel(fake)
        model.load("b-1")
        advanceUntilIdle()
        model.label("  Half-yearly exam ")
        model.amount("500")
        model.exam("x-1")
        model.dueOn("2026-11-20")
        model.choose("e-2", SeatChoice.WAIVE)
        model.choose("e-3", SeatChoice.LEAVE_OUT)

        model.raise()
        advanceUntilIdle()

        val (batch, sent) = fake.raised.single()
        assertEquals("b-1", batch)
        assertEquals("exam", sent.purpose)
        assertEquals("Half-yearly exam", sent.label)
        assertEquals("x-1", sent.examId)
        assertEquals(Money.of("500.00"), sent.amount)
        assertEquals("2026-11-20", sent.dueOn)
        assertEquals(listOf(SeatAmountDto("e-2", Money.ZERO)), sent.seatAmounts)
        assertEquals(listOf("e-3"), sent.excludedEnrollmentIds)
        assertEquals("key-1", sent.clientMutationId)
        assertNotNull(model.state.value.raised)
    }

    @Test
    fun `choosing charge again clears a student's choice`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.Ok(students())
        val model = raiseModel(fake)
        model.load("b-1")
        advanceUntilIdle()

        model.choose("e-1", SeatChoice.WAIVE)
        model.choose("e-1", SeatChoice.CHARGE)
        model.choose("e-unknown", SeatChoice.LEAVE_OUT)

        assertTrue(model.state.value.choices.isEmpty())
    }

    @Test
    fun `an other fee is linked to no exam`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.Ok(students())
        fake.exams = AuthResult.Ok(listOf(exam("x-1")))
        val model = raiseModel(fake)
        model.load("b-1")
        advanceUntilIdle()
        model.exam("x-1")

        model.kind(FeeKind.OTHER)
        model.label("Printing")
        model.amount("50")
        model.raise()
        advanceUntilIdle()

        assertNull(model.state.value.examId)
        assertEquals("other", fake.raised.single().second.purpose)
        assertNull(fake.raised.single().second.examId)
    }

    @Test
    fun `an exam the batch does not have cannot be linked`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.Ok(students())
        val model = raiseModel(fake)
        model.load("b-1")
        advanceUntilIdle()

        model.exam("x-other")

        assertNull(model.state.value.examId)
    }

    @Test
    fun `a resend after a failure reuses the form's retry key`() = runTest(dispatcher) {
        val fake = Fake()
        fake.batch = AuthResult.Ok(students())
        fake.raiseResult = AuthResult.TransportFailure
        val model = raiseModel(fake)
        model.load("b-1")
        advanceUntilIdle()
        model.label("Exam")
        model.amount("500")

        model.raise()
        advanceUntilIdle()
        assertEquals("error.network.unreachable", model.state.value.failureKey)
        assertFalse(model.state.value.saving)

        fake.raiseResult = refusal("extra_fee.label_required")
        model.raise()
        advanceUntilIdle()

        assertEquals(listOf("key-1", "key-1"), fake.raised.map { it.second.clientMutationId })
        assertEquals("extra_fee.label_required", model.state.value.failureKey)
        assertNull(model.state.value.raised)
    }

    // ----------------------------------------------------------- detail

    @Test
    fun `recording opens at what the student owes on the fee and is tagged with it`() = runTest(dispatcher) {
        val fake = Fake()
        val recorder = Recorder()
        val model = ExtraFeeDetailViewModel(fake, recorder, newMutationId = { "rec-1" })
        model.load("f-1")
        advanceUntilIdle()
        val fee = assertIs<ExtraFeeDetailUiState.Loaded>(model.state.value).fee

        model.openRecord(fee.students.first { it.enrollmentId == "e-2" })
        val sheet = assertNotNull(model.sheet.value)
        assertEquals(Money.of("300.00"), sheet.owed)
        assertEquals("300", sheet.typed)

        model.confirmRecord()
        advanceUntilIdle()

        val (seat, body) = recorder.sent.single()
        assertEquals("e-2", seat)
        assertEquals(Money.of("300.00"), body.amount)
        assertEquals("extra", body.purpose)
        assertEquals("f-1", body.extraFeeId)
        assertEquals("rec-1", body.clientMutationId)
        assertNull(model.sheet.value)
        assertTrue(model.recorded.value)
        assertEquals(2, fake.detailReads, "the fee is read again after the record")
    }

    @Test
    fun `a short record needs a carry-or-waive before it can be sent`() = runTest(dispatcher) {
        val fake = Fake()
        val recorder = Recorder()
        val model = ExtraFeeDetailViewModel(fake, recorder)
        model.load("f-1")
        advanceUntilIdle()
        model.openRecord(assertIs<ExtraFeeDetailUiState.Loaded>(model.state.value).fee.students[1])

        model.typeRecordAmount("100")
        model.confirmRecord()
        advanceUntilIdle()
        assertTrue(recorder.sent.isEmpty())

        model.chooseRecordDisposition("waived")
        model.confirmRecord()
        advanceUntilIdle()
        assertEquals("waived", recorder.sent.single().second.shortfallDisposition)
    }

    @Test
    fun `a refused record keeps the sheet open with the reason`() = runTest(dispatcher) {
        val fake = Fake()
        val recorder = Recorder()
        recorder.reply = refusal("fees.extra.overpaid")
        val model = ExtraFeeDetailViewModel(fake, recorder)
        model.load("f-1")
        advanceUntilIdle()
        model.openRecord(assertIs<ExtraFeeDetailUiState.Loaded>(model.state.value).fee.students[1])
        model.typeRecordAmount("900")

        model.confirmRecord()
        advanceUntilIdle()

        assertEquals("fees.extra.overpaid", model.sheet.value?.errorKey)
        assertFalse(model.recorded.value)
    }

    @Test
    fun `an offline fee read can be retried`() = runTest(dispatcher) {
        val fake = Fake()
        fake.detail = AuthResult.TransportFailure
        val model = ExtraFeeDetailViewModel(fake, Recorder())
        model.load("f-1")
        advanceUntilIdle()
        assertEquals(ExtraFeeDetailUiState.Failed("error.network.unreachable", true), model.state.value)

        fake.detail = AuthResult.Ok(detail())
        model.retry()
        advanceUntilIdle()
        assertIs<ExtraFeeDetailUiState.Loaded>(model.state.value)
    }

    companion object {
        fun summary(id: String = "f-1") =
            ExtraFeeSummaryDto(
                extraFeeId = id,
                purpose = "exam",
                label = "Half-yearly exam",
                examTitle = null,
                amount = Money.of("500.00"),
                dueOn = "2026-11-20",
                studentCount = 2,
                paidCount = 1,
                owingCount = 1,
                chargedTotal = Money.of("1000.00"),
                collectedTotal = Money.of("700.00"),
                owedTotal = Money.of("300.00"),
            )

        fun detail() =
            ExtraFeeDetailDto(
                extraFeeId = "f-1",
                purpose = "exam",
                label = "Half-yearly exam",
                amount = Money.of("500.00"),
                dueOn = "2026-11-20",
                chargedTotal = Money.of("1000.00"),
                collectedTotal = Money.of("700.00"),
                owedTotal = Money.of("300.00"),
                students =
                    listOf(
                        ExtraFeeStudentDto("e-1", "Tanvir", Money.of("500.00"), Money.of("500.00"), Money.ZERO, "paid"),
                        ExtraFeeStudentDto(
                            "e-2",
                            "Tania",
                            Money.of("500.00"),
                            Money.of("200.00"),
                            Money.of("300.00"),
                            "partly_paid",
                        ),
                    ),
            )
    }
}
