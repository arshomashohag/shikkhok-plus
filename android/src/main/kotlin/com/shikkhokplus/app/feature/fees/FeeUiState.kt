package com.shikkhokplus.app.feature.fees

import com.shikkhokplus.app.core.model.Money

/**
 * One fee period as the screen renders it.
 *
 * **`statusLabel` is a string resource key chosen from the server's
 * enum, never computed from [outstanding]** [BR6.1, TC-9, D-31]. The
 * temptation is `if (outstanding > Money.ZERO) "Due" else "Paid"`, and
 * it is wrong twice over: it is a business rule about what counts as
 * due written where it looks like presentation, and it reports a fully
 * waived cycle — zero balance, nobody paid — as "Paid".
 *
 * `charged` and `outstanding` stay [Money] all the way to the
 * renderer. Converting to a string here would move the rendering
 * decision onto the client; converting to a number would lose
 * exactness [TC-7].
 *
 * @property period The calendar month as `YYYY-MM`
 * @property periodLabel What the row shows for that month
 * @property dueDateLabel The due date as the server sent it
 * @property charged What was charged
 * @property outstanding What is still owed
 * @property statusLabel A string resource key for the status
 * @property isSettled Whether anything is still owed, **decided by the
 *   mapper from the server's status rather than by the composable from
 *   the amount**. A screen that dimmed a row by comparing a balance
 *   would be deriving the same rule the enum exists to carry
 */
data class FeeCycleRow(
    val period: String,
    val periodLabel: String,
    val dueDateLabel: String,
    val charged: Money,
    val outstanding: Money,
    val statusLabel: String,
    val isSettled: Boolean,
)

/**
 * One seat's fee position on the teacher's roster.
 *
 * **Carries no collection number** [BR6.4]: the teacher reads their own
 * payment destination on the batch screen, and this row reaches a list.
 *
 * @property enrollmentId The teacher-facing key
 * @property displayName The teacher-typed name
 * @property outstanding What this seat owes in total
 * @property statusLabel The latest period's status key, or null when
 *   nothing has generated yet
 * @property dueDateLabel The latest period's due date, or null
 * @property owesSomething Whether this seat owes anything, **decided
 *   here** so no composable compares the amount to pick a colour
 */
data class RosterFeeRow(
    val enrollmentId: String,
    val displayName: String,
    val outstanding: Money,
    val statusLabel: String?,
    val dueDateLabel: String?,
    val owesSomething: Boolean,
)

/**
 * What the payment form needs in order to let somebody pay.
 *
 * **Absent rather than present-with-null** [NFR14.34]: where the
 * teacher set no collection number the state is
 * [PaymentDestination.Unset], and the screen omits the destination step
 * and tells the person to ask the teacher. A nullable field here would
 * invite a placeholder in its place.
 */
sealed interface PaymentDestination {
    /** The teacher set a number; here is where and how to pay. */
    data class Known(
        val collectionNumber: String,
        val collectionChannelLabel: String?,
        val channels: List<String>,
    ) : PaymentDestination

    /**
     * The teacher set none, so there is no destination step at all.
     *
     * @property messageKey What to tell the person instead
     */
    data class Unset(
        val messageKey: String = "fees.destination.ask_teacher",
    ) : PaymentDestination
}

/**
 * A submitted claim and its outcome, as its submitter sees it.
 *
 * @property claimId The claim
 * @property period Which period it was for
 * @property claimedAmount What was claimed
 * @property approvedAmount What was accepted, or null while pending
 * @property statusLabel A string resource key for the outcome
 * @property dispositionLabel A key for carried or waived, where one
 *   applies, or null
 * @property channelLabel Which service the money moved through
 * @property isDecided Whether a teacher has decided it yet, **decided
 *   here from the status enum** rather than by a composable testing
 *   whether `approvedAmount` is null
 * @property correctionNoticeKey Set when a previous decision exists, so
 *   the screen shows that the verification was corrected [BR5.7]. The
 *   correction is visible to the teacher AND to the student and
 *   guardian; hiding it from either is the asymmetry FR9.2 forbids
 */
data class ClaimRow(
    val claimId: String,
    val period: String,
    val claimedAmount: Money,
    val approvedAmount: Money?,
    val statusLabel: String,
    val dispositionLabel: String?,
    val channelLabel: String,
    val isDecided: Boolean,
    val correctionNoticeKey: String?,
)

/**
 * Everything the fee screens can be showing.
 *
 * A sealed hierarchy rather than a struct of nullables, so a `when`
 * over it is exhaustive and a new state cannot be rendered as a blank
 * screen.
 */
sealed interface FeeUiState {
    /** The first load, with nothing to show yet. */
    data object Loading : FeeUiState

    /**
     * The seat has no generated period at all.
     *
     * A distinct state rather than an empty list, because the copy
     * differs: nothing is owed because nothing has been charged yet,
     * which is not the same as everything being paid.
     */
    data object Empty : FeeUiState

    /**
     * Periods to show.
     *
     * @property rows The periods, newest first
     * @property totalOutstanding What is owed across all of them,
     *   **as the server computed it** — not a sum over [rows], which
     *   would be the client doing money arithmetic [TC-9]
     */
    data class Loaded(
        val rows: List<FeeCycleRow>,
        val totalOutstanding: Money,
    ) : FeeUiState

    /**
     * The load failed.
     *
     * @property messageKey A string resource key, never server English
     * @property retryable Whether retrying could help, **told by the
     *   server** rather than inferred from a status code [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : FeeUiState
}
