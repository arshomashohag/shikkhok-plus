package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ClaimQueueItemDto
import com.shikkhokplus.app.core.network.DuplicateClaimDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RecentDecisionDto
import com.shikkhokplus.app.core.network.ShortfallPreviewDto
import com.shikkhokplus.app.core.network.VerificationQueueDto
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
import kotlin.test.assertNull

/**
 * T4's behaviour: what each action sends, and what it never does.
 *
 * **Approving a short claim must not send.** Approving less than the
 * charge needs carry or waive [BR5.4]; sending it bare would be refused,
 * and approving the charge instead would record money nobody received.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class VerifyViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun claim(
        id: String = "c-1",
        comparison: String = "matches",
        claimed: String = "1200.00",
        duplicate: DuplicateClaimDto? = null,
    ) = ClaimQueueItemDto(
        claimId = id,
        enrollmentId = "e-1",
        displayName = "Tasnim",
        batchName = "Physics A",
        period = "2026-10",
        claimedAmount = Money.of(claimed),
        charged = Money.of("1200.00"),
        comparison = comparison,
        difference = Money.of(if (comparison == "matches") "0.00" else "400.00"),
        channel = "bKash",
        transactionId = "BJK40OQ1IL",
        submittedAt = "2026-10-28T10:00:00Z",
        submittedBy = "guardian",
        submitterPhone = "+8801711234567",
        duplicateOf = duplicate,
    )

    private class Fake(
        var queue: AuthResult<VerificationQueueDto>,
        var decision: AuthResult<Unit> = AuthResult.Ok(Unit),
    ) : VerifyRepository {
        val approvals = mutableListOf<Triple<String, Money, String?>>()
        val rejections = mutableListOf<String>()
        val previews = mutableListOf<Money>()

        override suspend fun queue(): AuthResult<VerificationQueueDto> = queue

        override suspend fun preview(claimId: String, approvedAmount: Money): AuthResult<ShortfallPreviewDto> {
            previews += approvedAmount
            val short = Money.of("1200.00").amount - approvedAmount.amount
            return AuthResult.Ok(
                ShortfallPreviewDto(Money(short.max(java.math.BigDecimal.ZERO).setScale(2)), short.signum() > 0),
            )
        }

        override suspend fun approve(claimId: String, approvedAmount: Money, disposition: String?): AuthResult<Unit> {
            approvals += Triple(claimId, approvedAmount, disposition)
            return decision
        }

        override suspend fun reject(claimId: String): AuthResult<Unit> {
            rejections += claimId
            return decision
        }
    }

    private fun shortClaim() = claim(comparison = "short", claimed = "800.00")

    private fun refused(key: String) = AuthResult.Refused(ErrorEnvelope(ErrorBody("CONFLICT", false, key)))

    private fun loaded(fake: Fake): VerifyViewModel = VerifyViewModel(fake).also { it.load() }

    @Test
    fun `a matching claim is approved at the amount sent`() = runTest(dispatcher) {
        val fake = Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(claim()))))
        val model = loaded(fake)
        advanceUntilIdle()
        val card = assertIs<VerifyUiState.Waiting>(model.state.value).pending.single()

        model.approve(card)
        advanceUntilIdle()

        assertEquals(listOf(Triple<String, Money, String?>("c-1", Money.of("1200.00"), null)), fake.approvals)
    }

    @Test
    fun `approving a short claim opens the sheet and sends nothing`() = runTest(dispatcher) {
        val fake = Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(shortClaim()))))
        val model = loaded(fake)
        advanceUntilIdle()
        val card = assertIs<VerifyUiState.Waiting>(model.state.value).pending.single()

        model.approve(card)
        advanceUntilIdle()

        assertEquals(emptyList<Triple<String, Money, String?>>(), fake.approvals)
        val sheet = requireNotNull(model.sheet.value)
        assertEquals(Money.of("400.00"), sheet.shortfall)
        assertEquals(true, sheet.dispositionRequired)
    }

    @Test
    fun `a partial approval sends the chosen disposition, and not before`() = runTest(dispatcher) {
        val fake = Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(shortClaim()))))
        val model = loaded(fake)
        advanceUntilIdle()
        model.approve(assertIs<VerifyUiState.Waiting>(model.state.value).pending.single())
        advanceUntilIdle()

        model.confirmPartial()
        advanceUntilIdle()
        assertEquals(emptyList<Triple<String, Money, String?>>(), fake.approvals, "no disposition chosen yet")

        model.choose("waived")
        model.confirmPartial()
        advanceUntilIdle()

        assertEquals(listOf(Triple<String, Money, String?>("c-1", Money.of("800.00"), "waived")), fake.approvals)
        assertNull(model.sheet.value)
    }

    @Test
    fun `typing a new amount asks the server again`() = runTest(dispatcher) {
        val fake = Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(claim()))))
        val model = loaded(fake)
        advanceUntilIdle()
        model.openPartial(assertIs<VerifyUiState.Waiting>(model.state.value).pending.single())
        advanceUntilIdle()

        model.typePartial("1000")
        advanceUntilIdle()

        assertEquals(listOf(Money.of("1200.00"), Money.of("1000.00")), fake.previews)
        assertEquals(Money.of("200.00"), model.sheet.value?.shortfall)
    }

    @Test
    fun `a refused decision keeps the list and says why`() = runTest(dispatcher) {
        val fake =
            Fake(
                AuthResult.Ok(VerificationQueueDto(pending = listOf(claim()))),
                decision = refused("fees.claim.already_decided"),
            )
        val model = loaded(fake)
        advanceUntilIdle()
        val card = assertIs<VerifyUiState.Waiting>(model.state.value).pending.single()

        model.reject(card)
        advanceUntilIdle()

        val state = assertIs<VerifyUiState.Waiting>(model.state.value)
        assertEquals("fees.claim.already_decided", state.errorKey)
        assertEquals(1, state.pending.size)
        assertEquals(listOf("c-1"), fake.rejections)
    }

    @Test
    fun `an empty queue is all caught up and keeps the recent decisions`() = runTest(dispatcher) {
        val recent =
            RecentDecisionDto(
                "c-9",
                "Mehjabin",
                "Maths B",
                "approved_full",
                Money.of("1500.00"),
                "2026-10-28T03:14:00Z",
            )
        val model = loaded(Fake(AuthResult.Ok(VerificationQueueDto(decidedRecently = listOf(recent)))))
        advanceUntilIdle()

        val state = assertIs<VerifyUiState.AllCaughtUp>(model.state.value)
        assertEquals("verify.decision.approved_full", state.recent.single().statusKey)
    }

    @Test
    fun `an unknown comparison is a failure, not a guess`() = runTest(dispatcher) {
        val model = loaded(Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(claim(comparison = "maybe"))))))
        advanceUntilIdle()

        assertIs<VerifyUiState.Failed>(model.state.value)
    }

    @Test
    fun `a duplicate reference reaches the card with the earlier claim`() = runTest(dispatcher) {
        val duplicate = DuplicateClaimDto("c-0", "Sakib", "approved_full", Money.of("1500.00"), "2026-10-12T09:00:00Z")
        val model = loaded(Fake(AuthResult.Ok(VerificationQueueDto(pending = listOf(claim(duplicate = duplicate))))))
        advanceUntilIdle()

        val card = assertIs<VerifyUiState.Waiting>(model.state.value).pending.single()
        assertEquals("Sakib", card.duplicate?.displayName)
        assertEquals("verify.from.guardian", card.submitterKey)
    }

    @Test
    fun `an offline read can be retried`() = runTest(dispatcher) {
        val fake = Fake(AuthResult.TransportFailure)
        val model = loaded(fake)
        advanceUntilIdle()
        assertIs<VerifyUiState.Failed>(model.state.value)

        fake.queue = AuthResult.Ok(VerificationQueueDto())
        model.retry()
        advanceUntilIdle()

        assertIs<VerifyUiState.AllCaughtUp>(model.state.value)
    }
}
