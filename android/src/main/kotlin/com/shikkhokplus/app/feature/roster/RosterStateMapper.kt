package com.shikkhokplus.app.feature.roster

import com.shikkhokplus.app.core.model.LinkState
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RosterRowDto

/**
 * Maps server responses to a [RosterUiState].
 *
 * **This function is the unit under test**, rather than "the
 * ViewModel". It is pure: no network, no storage, no clock. A decision
 * needing any of those would be a business rule, and business rules are
 * server-side [TC-9, D-31].
 */
object RosterStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be parsed. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /** The server's code for a seat somebody accepted [BR3.2]. */
    const val CLAIMED_CODE: String = "ENROLLMENT_CLAIMED"

    /** The server's code for a seat whose holder erased [BR3.2]. */
    const val ERASED_CODE: String = "ENROLLMENT_ERASED"

    /**
     * String resource keys for the three server-decided statuses.
     *
     * **The mapping is exhaustive and an unknown value is an error**,
     * not a silent default. A server that added a fourth status would
     * otherwise render every new seat under whichever label happened to
     * be the fallback, which is worse than showing nothing.
     */
    private val STATUS_KEYS: Map<String, String> =
        mapOf(
            "dormant" to "roster.status.dormant",
            "active" to "roster.status.active",
            "inactive" to "roster.status.inactive",
        )

    /**
     * Map a loaded roster.
     *
     * **The counts are carried through, never computed** [BR1.3]. The
     * temptation here is `rows.count { it.studentState == "accepted" }`,
     * which is the client deciding what counts as accepted and would be
     * wrong the moment the roster paginates [NFR20.9].
     *
     * @param batchName Which class this is
     * @param rows The seats the server returned
     * @param fetchedAtLabel When this was fetched, or null when live
     * @param accepted The server's two counts, or null when this read
     *   did not carry the batch summary
     * @return The state the screen renders
     */
    fun afterLoad(
        batchName: String,
        rows: List<RosterRowDto>,
        fetchedAtLabel: String? = null,
        accepted: AcceptedCount? = null,
    ): RosterUiState {
        if (rows.isEmpty()) {
            return RosterUiState.Empty(batchName)
        }

        val mapped =
            rows.map { row ->
                toRow(row)
                    ?: return RosterUiState.Failed(UNEXPECTED_KEY, retryable = false)
            }
        return RosterUiState.Loaded(batchName, mapped, fetchedAtLabel, accepted)
    }

    /**
     * Convert one seat, or null when the server sent a value we do not
     * recognise.
     *
     * **Every decision this row carries is made here**, which is the
     * whole reason the function exists: a composable comparing
     * `studentState == DECLINED` to choose a mark would be holding a
     * business rule, and that is the slip D1 made on `InvitationCard`
     * and corrected. D2 renders four times as many states, so the same
     * shape would present four times as often.
     *
     * **The two link states map exhaustively or fail**, exactly as
     * `status` already does. A server that added a fifth value would
     * otherwise render every such seat under whichever branch happened
     * to be the fallback -- and here the fallback would be a claim
     * about somebody's answer.
     *
     * @param dto The seat the server returned
     * @return The row, or null for an unrecognised value
     */
    private fun toRow(dto: RosterRowDto): RosterRow? {
        val label = STATUS_KEYS[dto.status] ?: return null
        val student = LinkState.fromWire(dto.studentState) ?: return null
        val guardian = LinkState.fromWire(dto.guardianState) ?: return null

        // A seat always HAS a student link -- that is what the seat is
        // -- so `absent` on it is a contract failure rather than a seat
        // to render. Refused here rather than rendered as something.
        if (student == LinkState.ABSENT) return null

        val declined =
            student == LinkState.DECLINED || guardian == LinkState.DECLINED

        return RosterRow(
            enrollmentId = dto.enrollmentId,
            displayName = dto.displayName,
            statusLabel = label,
            fee = dto.feeAmount,
            guardianPhone = dto.guardianPhone,
            studentState = student,
            guardianState = guardian,
            // **The number for a declined seat, the name otherwise**
            // [BR2.3, ADR-012, NFR14.28]. The name is RETAINED as the
            // teacher's record of who they meant to add -- the
            // commonest cause of a decline is a mistyped number they
            // need to correct -- and it is not DISPLAYED, because it
            // names a person who has said the seat is not theirs.
            //
            // When no number was recorded there is nothing to show in
            // its place, so the row shows a placeholder rather than
            // falling back to the name. BR2.3 states its own violation
            // as "a name is displayed for a person who has said the
            // seat is not theirs", and a student-side decline on a
            // seat with no guardian number is exactly that case:
            // `guardian_phone` is nullable, so the branch is reachable
            // and the fallback would produce the violation verbatim.
            displayLabel = if (declined) dto.guardianPhone else dto.displayName,
            // Declined is marked per row because it is abnormal and
            // usually means a mistyped number. Pending is NOT, because
            // it is the normal state of a new seat and marking most
            // rows would flag normality as a problem [BR1.1,
            // AC1.3.3a] -- the batch-level count is pending's channel.
            isDeclined = declined,
            // READ, never derived [BR3.1]. Deriving it from the two
            // states above would offer removal on an erased seat,
            // whose marker this row never carries.
            isRemovable = dto.isRemovable,
        )
    }

    /**
     * Begin a removal, naming the seat being removed.
     *
     * @param row The seat the teacher chose
     * @return The confirmation state
     */
    fun beforeRemoval(row: RosterRow): RosterUiState =
        RosterUiState.ConfirmingRemoval(row)

    /**
     * Map a refused removal to its remedy.
     *
     * **The role-dependent half of [BR3.2], resolved once, here.** The
     * server returns two codes because the remedies differ: a claimed
     * seat can be marked inactive and the record stands [ADR-003], an
     * erased one cannot be reused at all. Deciding it in the mapper
     * rather than in a composable is what makes it testable and what
     * stops a second screen getting it wrong independently.
     *
     * An unrecognised code falls back to [RosterUiState.Failed] rather
     * than guessing a remedy: telling a teacher to mark a seat inactive
     * when that is not the remedy is worse than telling them nothing.
     *
     * @param row The seat that was not removed
     * @param envelope The server's refusal
     * @return The refusal state carrying its remedy, or a failure
     */
    fun afterRemovalRefused(
        row: RosterRow,
        envelope: ErrorEnvelope,
    ): RosterUiState {
        val remedy =
            when (envelope.error.code) {
                CLAIMED_CODE -> RemovalRemedy.MARK_INACTIVE
                ERASED_CODE -> RemovalRemedy.NONE
                else -> return afterError(envelope)
            }
        return RosterUiState.RemovalRefused(
            row = row,
            messageKey = envelope.error.messageKey,
            remedy = remedy,
        )
    }

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
    fun afterError(envelope: ErrorEnvelope): RosterUiState =
        RosterUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * Always retryable: there is no local write queue in V1, so the
     * screen must offer an explicit retry rather than appearing to have
     * succeeded [TC-8, D-9].
     *
     * @return The offline state
     */
    fun afterTransportFailure(): RosterUiState =
        RosterUiState.Failed(OFFLINE_KEY, retryable = true)
}
