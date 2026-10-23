package com.shikkhokplus.app.feature.roster

import com.shikkhokplus.app.core.model.LinkState
import com.shikkhokplus.app.core.model.Money

/**
 * The two numbers behind "9 of 12 accepted" [AC1.3.5a].
 *
 * **Both counted by the server, neither derived here** [BR1.2, BR1.3].
 * A type rather than two loose `Int`s so the pair travels together and
 * a call site cannot format the numerator against a denominator it
 * computed itself.
 *
 * @property accepted Seats at least one link has accepted
 * @property total Every seat the teacher created, **including declined
 *   ones** [BR1.4]. Excluding them would make the denominator shrink
 *   silently as people decline, so "9 of 12" becomes "9 of 11" with
 *   nothing having been removed
 */
data class AcceptedCount(
    val accepted: Int,
    val total: Int,
)

/**
 * Why a removal was refused, and therefore what the teacher can do.
 *
 * **Two refusals, two remedies, and this type exists so the screen
 * cannot show one message for both** [BR3.2]. The server already
 * returns distinct codes for exactly this reason; D2 is where the
 * difference reaches a person, and a single "could not remove" would
 * leave a teacher trying the remedy that cannot work.
 *
 * An exhaustive enum rather than a nullable flag, so a `when` over it
 * fails to compile if a third refusal ever appears rather than quietly
 * rendering one of the two existing remedies.
 */
enum class RemovalRemedy {
    /**
     * Somebody accepted the seat, so the record stands [ADR-003].
     *
     * The remedy is to mark the seat inactive instead [FR1.9i]: the
     * history is kept and no future fee cycle generates.
     */
    MARK_INACTIVE,

    /**
     * The account was erased, and the seat cannot be reused at all.
     *
     * There is no remedy to offer. Deleting the row would destroy the
     * marker that stops that number reattaching [BR6.2], so the honest
     * message is that this one stays as it is.
     */
    NONE,
}

/**
 * One roster row as the screen renders it.
 *
 * **`statusLabel` is a string resource key, not text**, and it is
 * chosen from the server's `status` enum rather than computed from
 * `inactiveFrom`. A client that decided "inactive" by comparing a date
 * would be holding a business rule [TC-9, D-31].
 *
 * `fee` stays a [Money] all the way to the renderer: converting it to a
 * string here would put the rendering decision on the client, and
 * converting it to a number would lose exactness [TC-7].
 *
 * @property enrollmentId The teacher-facing key
 * @property displayName The teacher-typed name, retained as the
 *   teacher's own record of who they meant to add [ADR-012]. **Not
 *   what the screen shows** — see [displayLabel]
 * @property statusLabel A string resource key for the seat's status
 * @property fee This seat's fee, or null when it inherits
 * @property guardianPhone The teacher-typed guardian contact, if any
 * @property studentState The student link's own decision [BR2.1]
 * @property guardianState The guardian link's own decision, or
 *   [LinkState.ABSENT] when no guardian was recorded [BR2.2]
 * @property displayLabel What the row actually shows: the bare **number**
 *   for a declined seat, the name otherwise [BR2.3, ADR-012, NFR14.28].
 *
 *   **A decision the mapper makes, not a comparison the screen does.**
 *   A name names a person who has said the seat is not theirs; the
 *   number is what the teacher needs to see, because the commonest
 *   cause of a decline is a mistyped one they must correct. Retention
 *   and display are different decisions and only the first keeps the
 *   name.
 *
 *   **Null when a declined seat carries no recorded number**, which the
 *   screen renders as a placeholder. `guardian_phone` is nullable, so a
 *   student-side decline on a seat with no guardian recorded reaches
 *   this case, and falling back to the name there would produce BR2.3's
 *   own stated violation: a name displayed for a person who has said
 *   the seat is not theirs.
 * @property isDeclined Whether to mark this row [BR1.1, AC1.3.3a].
 *
 *   **A decision, not an inference.** A composable writing
 *   `if (studentState == DECLINED)` would be comparing a domain value
 *   to choose a control — the slip D1 made and corrected on
 *   `InvitationCard`, which D2 would otherwise repeat four times over.
 *   Declined is marked per row because it is abnormal; pending is not,
 *   because it is the normal state of a new seat and decorating most
 *   rows would flag normality as a problem.
 * @property isRemovable Whether to offer removal [BR3.1, NFR14.31].
 *
 *   **The server's decision, read and never derived.** It could be
 *   derived from the two link states today, and deriving it is the
 *   trap: the real rule lives in `remove_enrollment` and reads the
 *   erasure markers too [BR7.1], which this row does not carry. A
 *   client derivation would offer removal on a seat the server refuses.
 */
data class RosterRow(
    val enrollmentId: String,
    val displayName: String,
    val statusLabel: String,
    val fee: Money?,
    val guardianPhone: String?,
    val studentState: LinkState,
    val guardianState: LinkState,
    val displayLabel: String?,
    val isDeclined: Boolean,
    val isRemovable: Boolean,
)

/**
 * Everything the roster screen renders.
 *
 * The four states are the ones `team.md` requires every ViewModel to
 * ship tests for: loading, success, error, and the explicit retry path
 * for a failed write [TC-8, D-9]. There is no offline queue in V1, so a
 * failed write surfaces [Failed] with `retryable` rather than
 * succeeding locally and reconciling later.
 */
sealed interface RosterUiState {
    /** Nothing has been asked for yet. */
    data object Idle : RosterUiState

    /** A request is in flight. */
    data object Loading : RosterUiState

    /**
     * The roster loaded.
     *
     * [Empty] is a separate state rather than a success with no rows,
     * because an empty list and "this batch has no students yet" need
     * different screens and a blank list explains neither.
     *
     * @property batchName Which class this is
     * @property rows The seats, in the order the server returned them
     * @property accepted The two counts behind "9 of 12 accepted", or
     *   null when this read did not carry the batch summary.
     *
     *   **Both numbers are the SERVER's** [BR1.2, BR1.3]. Formatting is
     *   the screen's and the numbers are not: a `rows.count { ... }`
     *   anywhere on this surface would be the client deciding what
     *   counts as accepted, and it would be wrong the moment the roster
     *   paginates [NFR20.9]. Null rather than zeroes, so a read without
     *   the summary renders nothing instead of claiming "0 of 0".
     * @property fetchedAtLabel When this was fetched, for the staleness
     *   notice the cache requires
     */
    data class Loaded(
        val batchName: String,
        val rows: List<RosterRow>,
        val fetchedAtLabel: String?,
        val accepted: AcceptedCount? = null,
    ) : RosterUiState

    /**
     * The batch exists and holds no seats yet.
     *
     * @property batchName Which class this is
     */
    data class Empty(val batchName: String) : RosterUiState

    /**
     * A removal is awaiting confirmation.
     *
     * Carries the row so the confirmation can **name what is being
     * removed** rather than asking "are you sure?" about nothing in
     * particular [W4].
     *
     * @property row The seat being removed
     */
    data class ConfirmingRemoval(val row: RosterRow) : RosterUiState

    /**
     * The server refused the removal, with which remedy applies.
     *
     * **Carries the remedy, not just the message** [BR3.2]. Claimed and
     * erased refuse for different reasons with different remedies —
     * mark inactive, versus the seat cannot be reused at all — and a
     * screen showing one message for both leaves a teacher trying the
     * one that cannot work.
     *
     * There is no `retryable` here deliberately: both refusals are
     * conflicts, so repeating the request unchanged cannot succeed, and
     * a retry control would invite exactly that.
     *
     * @property row The seat that was not removed
     * @property messageKey Names a string resource for the refusal
     * @property remedy What the teacher can do instead
     */
    data class RemovalRefused(
        val row: RosterRow,
        val messageKey: String,
        val remedy: RemovalRemedy,
    ) : RosterUiState

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
    ) : RosterUiState
}
