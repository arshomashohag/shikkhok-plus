package com.shikkhokplus.app.feature.invitations

import com.shikkhokplus.app.core.model.AcceptanceState
import com.shikkhokplus.app.core.model.Money

/**
 * One unaccepted seat as the screen renders it.
 *
 * **`fee` stays a [Money] all the way to the renderer.** Converting it
 * to a string here would move the rendering decision onto the client,
 * and converting it to a number would lose exactness [TC-7, D-20].
 *
 * `state` is the server's decision about **this holder's own link**,
 * never the other's [BR5.2], and the screen switches on it rather than
 * inferring anything.
 *
 * @property enrollmentId The seat, which the decision routes key on
 * @property batchName The class being joined
 * @property subject The subjects taught, as the teacher named them
 * @property fee This seat's fee, or null when it inherits the batch
 *   default. Null is NOT zero: zero is a waiver
 * @property state This holder's own decision
 * @property heldAsGuardian Whether this holder is the guardian on the
 *   seat rather than the student. Carried per row because the decline
 *   confirmation differs by role [BR5.2], and server-decided: the
 *   invitation response states it
 * @property canDecline Whether a decline action belongs on this row.
 *
 *   **A decision, not an inference** [TC-9, D-31]. A composable that
 *   wrote `if (state == PENDING)` would be comparing a domain value to
 *   choose a control, which is the layer boundary this project holds:
 *   if the client is comparing a domain value, the server should have
 *   sent a decision. The mapper owns it here, where a test can target
 *   it, and the rule it encodes is [BR5.4] -- an already-declined seat
 *   keeps its accept action and offers no second decline.
 */
data class InvitationRow(
    val enrollmentId: String,
    val batchName: String,
    val subject: List<String>,
    val fee: Money?,
    val state: AcceptanceState,
    val canDecline: Boolean,
    val heldAsGuardian: Boolean,
)

/**
 * Which decline sheet a screen must show.
 *
 * **Two sheets, not one, and this type exists so the choice cannot be
 * forgotten** [BR5.2, AC1.14.1a]. A single confirmation written once
 * and shown to both roles told a guardian a debt was cancelled when it
 * was not: a guardian's decline withdraws the guardian's own lens and
 * leaves the student's obligation entirely intact.
 *
 * Making this an exhaustive enum rather than a nullable flag means a
 * `when` over it fails to compile if a third role ever appears, rather
 * than silently showing one of the two existing sheets.
 */
enum class DeclineSheet {
    /** Declining a seat held as the student. The fee stops being owed. */
    STUDENT,

    /**
     * Declining a seat held as the guardian.
     *
     * The student's obligation is untouched; only this guardian's lens
     * is withdrawn.
     */
    GUARDIAN,
}

/**
 * Everything the invitations screen renders.
 *
 * The states are the ones `team.md` requires of every ViewModel:
 * loading, success, error, and the explicit retry path for a failed
 * write [TC-8, D-9]. There is no offline write queue in V1, so a failed
 * accept or decline surfaces [Failed] with `retryable` rather than
 * appearing to have succeeded.
 */
sealed interface InvitationsUiState {
    /** Nothing has been asked for yet. */
    data object Idle : InvitationsUiState

    /** A request is in flight. */
    data object Loading : InvitationsUiState

    /**
     * Unaccepted seats were found.
     *
     * A **declined** seat appears here too, with its state, because
     * its holder may change their mind [BR5.4, AC1.13.1].
     *
     * @property rows The seats, in the order the server returned them
     */
    data class Loaded(val rows: List<InvitationRow>) : InvitationsUiState

    /**
     * There is nothing to answer.
     *
     * A separate state rather than a [Loaded] with no rows, because an
     * empty list and "you have no invitations" need different screens
     * and a blank list explains neither.
     */
    data object Empty : InvitationsUiState

    /**
     * One seat, opened in detail.
     *
     * @property row The seat being answered
     */
    data class Detail(val row: InvitationRow) : InvitationsUiState

    /**
     * A decline is awaiting confirmation.
     *
     * Carries which [DeclineSheet] to show, decided from the link the
     * holder holds rather than chosen by the composable.
     *
     * @property row The seat being declined
     * @property sheet Which confirmation this role must read
     */
    data class ConfirmingDecline(
        val row: InvitationRow,
        val sheet: DeclineSheet,
    ) : InvitationsUiState

    /**
     * The decision was recorded.
     *
     * @property enrollmentId The seat decided on
     * @property state What this holder's link now carries
     */
    data class Decided(
        val enrollmentId: String,
        val state: AcceptanceState,
        val batchName: String = "",
    ) : InvitationsUiState

    /**
     * Something failed, and the screen can say what to do about it.
     *
     * @property messageKey Names a string resource; never English text
     *   from the server, which could not be localized [TC-15, D-43]
     * @property retryable Read from the server's envelope, never
     *   inferred from a status code [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : InvitationsUiState
}
