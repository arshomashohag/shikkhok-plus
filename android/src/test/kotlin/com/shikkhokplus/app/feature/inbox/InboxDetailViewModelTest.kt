package com.shikkhokplus.app.feature.inbox

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.ExamBlockDto
import com.shikkhokplus.app.core.network.InboxDto
import com.shikkhokplus.app.core.network.NoticeBlockDto
import com.shikkhokplus.app.core.network.NotificationDetailDto
import com.shikkhokplus.app.core.network.PaymentBlockDto
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

/** The detail's mapping from the server's reply to what is drawn. */
@OptIn(ExperimentalCoroutinesApi::class)
class InboxDetailViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun detail(
        kind: String,
        available: Boolean = true,
        notice: NoticeBlockDto? = null,
        exam: ExamBlockDto? = null,
        payment: PaymentBlockDto? = null,
    ) = NotificationDetailDto(
        notificationId = "n-1",
        kind = kind,
        batchName = "Physics",
        createdAt = "2026-10-17T06:00:00Z",
        read = true,
        available = available,
        notice = notice,
        exam = exam,
        payment = payment,
    )

    private class Fake(var result: AuthResult<NotificationDetailDto>) : InboxRepository {
        override suspend fun inbox(): AuthResult<InboxDto> = AuthResult.TransportFailure

        override suspend fun detail(id: String): AuthResult<NotificationDetailDto> = result

        override suspend fun markAllRead(): AuthResult<Unit> = AuthResult.Ok(Unit)

        override suspend fun markRead(id: String): AuthResult<Unit> = AuthResult.Ok(Unit)
    }

    @Test
    fun `an unavailable item maps to Unavailable`() = runTest(dispatcher) {
        val model = InboxDetailViewModel(Fake(AuthResult.Ok(detail("notice", available = false))))

        model.load("n-1")
        advanceUntilIdle()

        assertEquals(InboxDetailUiState.Unavailable, model.state.value)
    }

    @Test
    fun `a notice, an exam and a payment keep their words verbatim`() = runTest(dispatcher) {
        val notice = NoticeBlockDto("Bring a pen\nand paper", "2026-10-17T06:00:00Z", null)
        val exam = ExamBlockDto("e-1", "Mid-term", "2026-11-02", "Physics", 50, listOf("Motion", "Force"))
        val payment = PaymentBlockDto("c-1", "2026-10", Money.of("1200.00"), Money.of("800.00"), "partial", "Short")
        val models =
            listOf(
                detail("notice", notice = notice),
                detail("exam_scheduled", exam = exam),
                detail("payment_partial", payment = payment),
            ).map { InboxDetailViewModel(Fake(AuthResult.Ok(it))).also { m -> m.load("n-1") } }
        advanceUntilIdle()

        val contents = models.map { assertIs<InboxDetailUiState.Loaded>(it.state.value).detail.content }
        assertEquals("Bring a pen\nand paper", assertIs<InboxContent.Notice>(contents[0]).body)
        assertEquals(listOf("Motion", "Force"), assertIs<InboxContent.Exam>(contents[1]).topics)
        val paid = assertIs<InboxContent.Payment>(contents[2])
        assertEquals(PaymentOutcome.PARTIAL, paid.outcome)
        assertEquals(Money.of("800.00"), paid.approved)
        assertEquals("Short", paid.reason)
    }

    @Test
    fun `a failure carries the server's key and offline is retryable`() = runTest(dispatcher) {
        val refused =
            AuthResult.Refused(
                ErrorEnvelope(ErrorBody(code = "X", messageKey = "inbox.not_available", retryable = false)),
            )
        val a = InboxDetailViewModel(Fake(refused)).also { it.load("n-1") }
        val b = InboxDetailViewModel(Fake(AuthResult.TransportFailure)).also { it.load("n-1") }
        advanceUntilIdle()

        assertEquals(InboxDetailUiState.Failed("inbox.not_available", false), a.state.value)
        assertEquals(InboxDetailUiState.Failed(InboxMapper.OFFLINE_KEY, true), b.state.value)
    }
}
