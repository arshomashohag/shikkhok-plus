package com.shikkhokplus.app.feature.invitations

import com.shikkhokplus.app.core.model.AcceptanceState
import com.shikkhokplus.app.core.network.DecisionDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.InvitationDto

/**
 * Maps server responses to an [InvitationsUiState].
 *
 * **This object is the unit under test**, rather than "the ViewModel".
 * It is pure: no network, no storage, no clock. A decision needing any
 * of those would be a business rule, and business rules are server-side
 * [TC-9, D-31].
 */
object InvitationsStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be understood. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /**
     * Map a loaded invitation list.
     *
     * **An unknown `decision` is an error, not a silent default.** A
     * server that added a fourth state would otherwise render every
     * such seat under whichever value happened to be the fallback --
     * and the two values here are not interchangeable: showing a
     * declined seat as pending invites a person to answer a question
     * they already answered.
     *
     * @param rows The seats the server returned
     * @return The state the screen renders
     */
    fun afterLoad(rows: List<InvitationDto>): InvitationsUiState {
        if (rows.isEmpty()) {
            return InvitationsUiState.Empty
        }

        val mapped =
            rows.map { dto ->
                toRow(dto) ?: return InvitationsUiState.Failed(
                    UNEXPECTED_KEY,
                    retryable = false,
                )
            }
        return InvitationsUiState.Loaded(mapped)
    }

    /**
     * Map one seat opened in detail.
     *
     * @param dto The seat the server returned
     * @return The detail state, or a failure for an unknown decision
     */
    fun afterDetail(dto: InvitationDto): InvitationsUiState {
        val row =
            toRow(dto)
                ?: return InvitationsUiState.Failed(UNEXPECTED_KEY, retryable = false)
        return InvitationsUiState.Detail(row)
    }

    /**
     * Map a recorded decision.
     *
     * @param dto The server's answer
     * @return The decided state, or a failure for an unknown decision
     */
    fun afterDecision(dto: DecisionDto): InvitationsUiState {
        val state =
            AcceptanceState.fromWire(dto.decision)
                ?: return InvitationsUiState.Failed(UNEXPECTED_KEY, retryable = false)
        return InvitationsUiState.Decided(dto.enrollmentId, state)
    }

    /**
     * Choose which decline confirmation a holder must read.
     *
     * **The role-dependent rule, resolved once, here** [BR5.2,
     * AC1.14.1a]. A guardian's decline leaves the student's obligation
     * standing, so a guardian must not read a sheet saying the fee
     * stops. Deciding it in the mapper rather than in a composable is
     * what makes it testable and what stops a second screen getting it
     * wrong independently.
     *
     * @param row The seat being declined
     * @param heldAsGuardian Whether this holder holds the guardian link
     * @return The confirmation state, with its sheet chosen
     */
    fun beforeDecline(
        row: InvitationRow,
        heldAsGuardian: Boolean,
    ): InvitationsUiState =
        InvitationsUiState.ConfirmingDecline(
            row = row,
            sheet = if (heldAsGuardian) DeclineSheet.GUARDIAN else DeclineSheet.STUDENT,
        )

    /**
     * Map a server error envelope.
     *
     * `retryable` is **read from the envelope**, never inferred from a
     * status code: the client holds no business logic, so it is told
     * rather than deciding [TC-9].
     *
     * @param envelope The server's error
     * @return The state the screen renders
     */
    fun afterError(envelope: ErrorEnvelope): InvitationsUiState =
        InvitationsUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * Always retryable: there is no local write queue in V1, so a
     * failed accept must offer an explicit retry rather than appearing
     * to have succeeded [TC-8, D-9].
     *
     * @return The offline state
     */
    fun afterTransportFailure(): InvitationsUiState =
        InvitationsUiState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * Convert one seat, or null when its decision is unrecognised.
     *
     * @param dto The seat the server returned
     * @return The row, or null
     */
    private fun toRow(dto: InvitationDto): InvitationRow? {
        val state = AcceptanceState.fromWire(dto.decision) ?: return null
        return InvitationRow(
            enrollmentId = dto.enrollmentId,
            batchName = dto.batchName,
            subject = dto.subject,
            fee = dto.feeAmount,
            state = state,
            // Decided here rather than in the composable, so the screen
            // renders a decision instead of comparing a domain value
            // [TC-9, D-31]. An already-declined seat keeps its accept
            // action and offers no second decline [BR5.4].
            canDecline = state == AcceptanceState.PENDING,
            // **Read from the response, never inferred.** The server
            // states which link this account holds; the client sends a
            // lens hint but must not trust its own [TC-11, D-2], and
            // an unknown value falls to student rather than guessing
            // guardian — the sheet that would wrongly promise a fee
            // had stopped is the guardian one, so the safer default is
            // the student sheet, which the student case also needs.
            heldAsGuardian = dto.role == "guardian",
        )
    }
}
