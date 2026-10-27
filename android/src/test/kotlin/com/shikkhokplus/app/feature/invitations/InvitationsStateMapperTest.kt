package com.shikkhokplus.app.feature.invitations

import com.shikkhokplus.app.core.model.AcceptanceState
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.DecisionDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.InvitationDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * The mapping decisions, which is where the screen's behaviour lives.
 *
 * Targeting the mapper rather than "the ViewModel" is what `team.md`
 * asks for: the decisions are here and reachable without a dispatcher.
 *
 * The one that matters most is the decline-sheet test. A single
 * confirmation shown to both roles told a guardian a debt was cancelled
 * when it was not, and that defect is invisible to every other test in
 * this file.
 */
class InvitationsStateMapperTest {

    private fun invitation(
        decision: String = "pending",
        fee: Money? = null,
        role: String = "student",
    ): InvitationDto =
        InvitationDto(
            enrollmentId = "e-1",
            batchName = "Physics",
            subject = listOf("Physics"),
            feeAmount = fee,
            decision = decision,
            role = role,
        )

    @Test
    fun `an empty list is its own state, not a loaded list of none`() {
        // An empty list and "you have no invitations" need different
        // screens, and a blank list explains neither.
        assertIs<InvitationsUiState.Empty>(
            InvitationsStateMapper.afterLoad(emptyList()),
        )
    }

    @Test
    fun `a pending seat carries the three fields and its own state`() {
        val state =
            InvitationsStateMapper.afterLoad(
                listOf(invitation(fee = Money.of("1200.00"))),
            )

        val row = assertIs<InvitationsUiState.Loaded>(state).rows.single()
        assertEquals("Physics", row.batchName)
        assertEquals(listOf("Physics"), row.subject)
        assertEquals(Money.of("1200.00"), row.fee)
        assertEquals(AcceptanceState.PENDING, row.state)
    }

    @Test
    fun `a declined seat stays listed and keeps its declined state`() {
        // BR5.4 and AC1.13.1: a decline is reversible by its holder, so
        // the seat must remain reachable with an accept action. A mapper
        // that dropped it, or relabelled it as pending, would turn a
        // mis-tap into a permanent lockout or re-ask a settled question.
        val state = InvitationsStateMapper.afterLoad(listOf(invitation("declined")))

        val row = assertIs<InvitationsUiState.Loaded>(state).rows.single()
        assertEquals(AcceptanceState.DECLINED, row.state)
    }

    @Test
    fun `an unknown decision fails loudly rather than defaulting`() {
        // Defaulting to PENDING would render a seat the person already
        // answered as if they had not. The two values are not
        // interchangeable, so there is no safe fallback.
        val state = InvitationsStateMapper.afterLoad(listOf(invitation("archived")))

        val failed = assertIs<InvitationsUiState.Failed>(state)
        assertEquals(InvitationsStateMapper.UNEXPECTED_KEY, failed.messageKey)
    }

    @Test
    fun `a student declining reads the student sheet`() {
        val row =
            InvitationRow(
                enrollmentId = "e-1",
                batchName = "Physics",
                subject = listOf("Physics"),
                fee = null,
                state = AcceptanceState.PENDING,
                canDecline = true,
                heldAsGuardian = false,
            )

        val state = InvitationsStateMapper.beforeDecline(row, heldAsGuardian = false)

        assertEquals(
            DeclineSheet.STUDENT,
            assertIs<InvitationsUiState.ConfirmingDecline>(state).sheet,
        )
    }

    @Test
    fun `a guardian declining reads the guardian sheet`() {
        // **THE ONE THIS FILE EXISTS FOR** [BR5.2, AC1.14.1a]. A
        // guardian's decline withdraws the guardian's own lens and
        // leaves the student's obligation entirely intact. One sheet
        // written once and shown to both roles told a guardian a debt
        // was cancelled when it was not.
        val row =
            InvitationRow(
                enrollmentId = "e-1",
                batchName = "Physics",
                subject = listOf("Physics"),
                fee = null,
                state = AcceptanceState.PENDING,
                canDecline = true,
                heldAsGuardian = false,
            )

        val state = InvitationsStateMapper.beforeDecline(row, heldAsGuardian = true)

        assertEquals(
            DeclineSheet.GUARDIAN,
            assertIs<InvitationsUiState.ConfirmingDecline>(state).sheet,
        )
    }

    @Test
    fun `a recorded decision reports the state the server returned`() {
        val state =
            InvitationsStateMapper.afterDecision(
                DecisionDto(enrollmentId = "e-1", decision = "accepted"),
            )

        val decided = assertIs<InvitationsUiState.Decided>(state)
        assertEquals("e-1", decided.enrollmentId)
        assertEquals(AcceptanceState.ACCEPTED, decided.state)
    }

    @Test
    fun `retryable is read from the envelope, never inferred`() {
        // The client holds no business logic: it is TOLD whether a
        // retry would help rather than deciding from a status code
        // [TC-9, D-31].
        val state =
            InvitationsStateMapper.afterError(
                ErrorEnvelope(
                    ErrorBody(
                        code = "NO_INVITATION_LENS",
                        retryable = false,
                        messageKey = "authz.lens.not_available",
                    ),
                ),
            )

        val failed = assertIs<InvitationsUiState.Failed>(state)
        assertEquals("authz.lens.not_available", failed.messageKey)
        assertEquals(false, failed.retryable)
    }

    @Test
    fun `a transport failure is always retryable`() {
        // There is no local write queue in V1, so a failed accept must
        // offer an explicit retry rather than appearing to have
        // succeeded [TC-8, D-9].
        val failed =
            assertIs<InvitationsUiState.Failed>(
                InvitationsStateMapper.afterTransportFailure(),
            )

        assertEquals(InvitationsStateMapper.OFFLINE_KEY, failed.messageKey)
        assertEquals(true, failed.retryable)
    }

    @Test
    fun `a pending seat may be declined`() {
        val loaded =
            assertIs<InvitationsUiState.Loaded>(
                InvitationsStateMapper.afterLoad(
                    listOf(invitation(decision = "pending")),
                ),
            )

        assertEquals(true, loaded.rows.single().canDecline)
    }

    @Test
    fun `a declined seat may NOT be declined again`() {
        // The decision belongs here rather than in the composable: a
        // screen writing `if (state == PENDING)` would be comparing a
        // domain value to choose a control, which is the layer boundary
        // [TC-9, D-31]. It still keeps its ACCEPT action, because a
        // decline is reversible by its holder [BR5.4].
        val loaded =
            assertIs<InvitationsUiState.Loaded>(
                InvitationsStateMapper.afterLoad(
                    listOf(invitation(decision = "declined")),
                ),
            )

        assertEquals(false, loaded.rows.single().canDecline)
    }
}
