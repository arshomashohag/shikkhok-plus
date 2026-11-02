package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.PaymentApprovalBodyDto
import com.shikkhokplus.app.core.network.PaymentReviewDto
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
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * R2 to R4: reviewing one payment.
 *
 * The server states what is owed and how the payment compares; the
 * model only decides which inputs the teacher must supply before the
 * server is asked to decide.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PaymentReviewViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake(
        var detail: AuthResult<PaymentReviewDto>,
        var decision: AuthResult<PaymentReviewDto>? = null,
    ) : PaymentReviewRepository {
        var reads = 0
        val approvals = mutableListOf<PaymentApprovalBodyDto>()
        val rejections = mutableListOf<Pair<String?, Boolean>>()

        override suspend fun detail(submissionId: String): AuthResult<PaymentReviewDto> {
            reads += 1
            return detail
        }

        override suspend fun approve(
            submissionId: String,
            body: PaymentApprovalBodyDto,
        ): AuthResult<PaymentReviewDto> {
            approvals += body
            return decision ?: detail
        }

        override suspend fun reject(
            submissionId: String,
            note: String?,
            correcting: Boolean,
        ): AuthResult<PaymentReviewDto> {
            rejections += note to correcting
            return decision ?: detail
        }
    }

    private fun ok(dto: PaymentReviewDto) = AuthResult.Ok(dto)

    private fun opened(fake: Fake): PaymentReviewViewModel =
        PaymentReviewViewModel(fake).also { it.load("s-1") }

    @Test
    fun `exact amount shows only approve`() = runTest(dispatcher) {
        val fake = Fake(ok(review()))
        val model = opened(fake)
        advanceUntilIdle()

        model.openSheet()
        val sheet = assertNotNull(model.sheet.value)

        assertFalse(sheet.needsDisposition)
        assertFalse(sheet.needsChild)
        assertTrue(sheet.canConfirm)
        model.confirmApproval()
        advanceUntilIdle()
        val sent = fake.approvals.single()
        assertEquals(Money.of("2000.00"), sent.receivedAmount)
        assertNull(sent.shortfallDisposition)
        assertNull(sent.carriedByEnrollmentId)
        assertNull(sent.creditToEnrollmentId)
        assertFalse(sent.correcting)
    }

    @Test
    fun `a matching payment is approved at once from the detail`() = runTest(dispatcher) {
        val fake = Fake(ok(review()))
        val model = opened(fake)
        advanceUntilIdle()

        model.approve()
        advanceUntilIdle()

        assertNull(model.sheet.value)
        assertEquals(Money.of("2000.00"), fake.approvals.single().receivedAmount)
    }

    @Test
    fun `short two children requires carry or waive and a child`() = runTest(dispatcher) {
        val fake = Fake(ok(review(comparison = "short", total = "1500.00", difference = "500.00")))
        val model = opened(fake)
        advanceUntilIdle()

        model.approve()
        val sheet = assertNotNull(model.sheet.value)
        assertTrue(sheet.needsDisposition)
        assertTrue(sheet.needsChild)
        assertFalse(sheet.canConfirm)
        model.confirmApproval()
        advanceUntilIdle()
        assertTrue(fake.approvals.isEmpty())

        model.chooseDisposition("carried")
        assertFalse(assertNotNull(model.sheet.value).canConfirm)
        model.chooseChild("e-2")
        assertTrue(assertNotNull(model.sheet.value).canConfirm)
        model.confirmApproval()
        advanceUntilIdle()

        val sent = fake.approvals.single()
        assertEquals(Money.of("1500.00"), sent.receivedAmount)
        assertEquals("carried", sent.shortfallDisposition)
        assertEquals("e-2", sent.carriedByEnrollmentId)
        assertNull(sent.creditToEnrollmentId)
    }

    @Test
    fun `short with one child needs a disposition but no child`() = runTest(dispatcher) {
        val one = listOf(reviewChild("e-1", "Rafsan", "2000.00"))
        val fake = Fake(ok(review(comparison = "short", total = "1500.00", children = one)))
        val model = opened(fake)
        advanceUntilIdle()

        model.approve()
        val sheet = assertNotNull(model.sheet.value)
        assertTrue(sheet.needsDisposition)
        assertFalse(sheet.needsChild)
        model.chooseDisposition("waived")
        assertTrue(assertNotNull(model.sheet.value).canConfirm)
    }

    @Test
    fun `over two children requires credit child`() = runTest(dispatcher) {
        val fake = Fake(ok(review(comparison = "over", total = "2500.00", difference = "500.00")))
        val model = opened(fake)
        advanceUntilIdle()

        model.approve()
        val sheet = assertNotNull(model.sheet.value)
        assertFalse(sheet.needsDisposition)
        assertTrue(sheet.needsChild)
        assertFalse(sheet.canConfirm)

        model.chooseChild("e-1")
        assertTrue(assertNotNull(model.sheet.value).canConfirm)
        model.confirmApproval()
        advanceUntilIdle()

        val sent = fake.approvals.single()
        assertEquals("e-1", sent.creditToEnrollmentId)
        assertNull(sent.carriedByEnrollmentId)
        assertNull(sent.shortfallDisposition)
    }

    @Test
    fun `typing a different amount recomputes which controls are needed`() = runTest(dispatcher) {
        val fake = Fake(ok(review()))
        val model = opened(fake)
        advanceUntilIdle()

        model.openSheet()
        model.typeAmount("1800")
        assertTrue(assertNotNull(model.sheet.value).needsDisposition)
        model.typeAmount("2000")
        assertFalse(assertNotNull(model.sheet.value).needsDisposition)
        model.typeAmount("abc")
        assertFalse(assertNotNull(model.sheet.value).canConfirm)
    }

    @Test
    fun `reject sends note`() = runTest(dispatcher) {
        val fake = Fake(ok(review()))
        val model = opened(fake)
        advanceUntilIdle()

        model.reject("Nothing arrived")
        advanceUntilIdle()

        assertEquals(listOf<Pair<String?, Boolean>>("Nothing arrived" to false), fake.rejections)
    }

    @Test
    fun `a blank rejection note is sent as no note`() = runTest(dispatcher) {
        val fake = Fake(ok(review()))
        val model = opened(fake)
        advanceUntilIdle()

        model.reject("   ")
        advanceUntilIdle()

        assertNull(fake.rejections.single().first)
    }

    @Test
    fun `decided shows note and change decision`() = runTest(dispatcher) {
        val fake = Fake(ok(review(status = "rejected", decisionNote = "Wrong number")))
        val model = opened(fake)
        advanceUntilIdle()

        val loaded = assertIs<ReviewUiState.Loaded>(model.state.value)
        assertEquals(ReviewStatus.REJECTED, loaded.card.status)
        assertEquals("Wrong number", loaded.card.decisionNote)
        assertFalse(loaded.canDecide)

        model.changeDecision()
        val changing = assertIs<ReviewUiState.Loaded>(model.state.value)
        assertTrue(changing.canDecide)

        model.reject("Still wrong")
        advanceUntilIdle()
        assertEquals(listOf<Pair<String?, Boolean>>("Still wrong" to true), fake.rejections)
    }

    @Test
    fun `a correction approval says it is correcting`() = runTest(dispatcher) {
        val fake = Fake(ok(review(status = "rejected", decisionNote = "Wrong number")))
        val model = opened(fake)
        advanceUntilIdle()

        model.changeDecision()
        model.approve()
        advanceUntilIdle()

        assertTrue(fake.approvals.single().correcting)
    }

    @Test
    fun `conflict reloads and explains`() = runTest(dispatcher) {
        val decided = review(status = "approved")
        val fake = Fake(ok(review()))
        fake.decision =
            AuthResult.Refused(
                ErrorEnvelope(ErrorBody("PAYMENT_ALREADY_DECIDED", false, "fees.verification.already_decided")),
            )
        val model = opened(fake)
        advanceUntilIdle()
        fake.detail = ok(decided)

        model.approve()
        advanceUntilIdle()

        assertEquals(2, fake.reads)
        val loaded = assertIs<ReviewUiState.Loaded>(model.state.value)
        assertEquals(ReviewStatus.APPROVED, loaded.card.status)
        assertEquals("fees.verification.already_decided", loaded.errorKey)
    }

    @Test
    fun `a failed write keeps the sheet for a retry`() = runTest(dispatcher) {
        val fake = Fake(ok(review(comparison = "over", total = "2500.00")))
        fake.decision = AuthResult.TransportFailure
        val model = opened(fake)
        advanceUntilIdle()

        model.approve()
        model.chooseChild("e-1")
        model.confirmApproval()
        advanceUntilIdle()

        assertNotNull(model.sheet.value)
        val loaded = assertIs<ReviewUiState.Loaded>(model.state.value)
        assertEquals(VerifyStateMapper.OFFLINE_KEY, loaded.errorKey)
        assertFalse(loaded.busy)

        fake.decision = ok(review(status = "approved"))
        model.confirmApproval()
        advanceUntilIdle()
        assertEquals(2, fake.approvals.size)
        assertNull(model.sheet.value)
    }

    @Test
    fun `an unreadable payment fails with the server's key`() = runTest(dispatcher) {
        val fake =
            Fake(AuthResult.Refused(ErrorEnvelope(ErrorBody("NOT_FOUND", false, "fees.not_available"))))
        val model = opened(fake)
        advanceUntilIdle()

        val failed = assertIs<ReviewUiState.Failed>(model.state.value)
        assertEquals("fees.not_available", failed.messageKey)
    }
}
