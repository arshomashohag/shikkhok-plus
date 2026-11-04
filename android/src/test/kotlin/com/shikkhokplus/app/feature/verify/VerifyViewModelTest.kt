package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.VerificationQueueDto
import com.shikkhokplus.app.core.network.PaymentReviewDto
import com.shikkhokplus.app.core.network.PaymentApprovalBodyDto
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

/** R1: the queue of payments waiting for the teacher. */
@OptIn(ExperimentalCoroutinesApi::class)
class VerifyViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake(var queue: AuthResult<VerificationQueueDto>) : VerifyRepository {
        override suspend fun queue(): AuthResult<VerificationQueueDto> = queue
    }

    @Test
    fun `waiting payments are listed by submission with the children together`() = runTest(dispatcher) {
        val model = VerifyViewModel(Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(review())))))
        model.load()
        advanceUntilIdle()

        val waiting = assertIs<VerifyUiState.Waiting>(model.state.value)
        val card = waiting.pending.single()
        assertEquals("s-1", card.submissionId)
        assertEquals("Rafsan, Tasnim", card.displayName)
    }

    @Test
    fun `nothing waiting is all caught up`() = runTest(dispatcher) {
        val model = VerifyViewModel(Fake(AuthResult.Ok(VerificationQueueDto())))
        model.load()
        advanceUntilIdle()

        assertIs<VerifyUiState.AllCaughtUp>(model.state.value)
    }

    @Test
    fun `an unknown comparison fails rather than guessing`() = runTest(dispatcher) {
        val model =
            VerifyViewModel(Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(review(comparison = "odd"))))))
        model.load()
        advanceUntilIdle()

        assertIs<VerifyUiState.Failed>(model.state.value)
    }

    @Test
    fun `a refusal carries the server's key and retry flag`() = runTest(dispatcher) {
        val refusal = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", true, "error.unexpected")))
        val model = VerifyViewModel(Fake(refusal))
        model.load()
        advanceUntilIdle()

        val failed = assertIs<VerifyUiState.Failed>(model.state.value)
        assertEquals(true, failed.retryable)
    }

    private class Decisions : PaymentReviewRepository {
        val approved = mutableListOf<Pair<String, String>>()

        override suspend fun detail(submissionId: String): AuthResult<PaymentReviewDto> = AuthResult.Ok(review())

        override suspend fun approve(submissionId: String, body: PaymentApprovalBodyDto): AuthResult<PaymentReviewDto> {
            approved += submissionId to body.receivedAmount.toString()
            return AuthResult.Ok(review(status = "approved"))
        }

        override suspend fun reject(submissionId: String, note: String?, correcting: Boolean) =
            AuthResult.Ok(review(status = "rejected"))
    }

    @Test
    fun `a matching payment is approved from the queue as reported, then the queue reloads`() =
        runTest(dispatcher) {
            val queue = Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(review()))))
            val decisions = Decisions()
            val model = VerifyViewModel(queue, decisions)
            model.load()
            advanceUntilIdle()
            val card = assertIs<VerifyUiState.Waiting>(model.state.value).pending.single()

            queue.queue = AuthResult.Ok(VerificationQueueDto())
            model.approveAsReported(card)
            advanceUntilIdle()

            assertEquals(listOf("s-1" to card.totalAmount.toString()), decisions.approved)
            assertIs<VerifyUiState.AllCaughtUp>(model.state.value)
            assertEquals(null, model.deciding.value)
        }

    @Test
    fun `a short payment is never approved from the queue`() = runTest(dispatcher) {
        // Short needs carry-forward or waive, which only the review asks.
        val decisions = Decisions()
        val model =
            VerifyViewModel(
                Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(review(comparison = "short"))))),
                decisions,
            )
        model.load()
        advanceUntilIdle()

        model.approveAsReported(assertIs<VerifyUiState.Waiting>(model.state.value).pending.single())
        advanceUntilIdle()

        assertEquals(emptyList(), decisions.approved)
    }
}
