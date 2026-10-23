package com.shikkhokplus.app.feature.guardian

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.GuardianChildDto

/**
 * Maps server responses to a [GuardianUiState].
 *
 * **This object is the unit under test**, rather than "the ViewModel".
 * It is pure: no network, no storage, no clock. A decision needing any
 * of those would be a business rule, and business rules are server-side
 * [TC-9, D-31].
 */
object GuardianStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be understood. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /**
     * Map a loaded child list.
     *
     * **The one-versus-several split is decided HERE** [frontend-
     * components]. A composable writing `if (children.size > 1)` would
     * be deciding whether a switcher is needed; the states are separate
     * so that decision is testable and made once.
     *
     * @param rows The seats the server returned
     * @return The state the screen renders
     */
    fun afterLoad(rows: List<GuardianChildDto>): GuardianUiState {
        val children = rows.map(::toChild)
        return when (children.size) {
            0 -> GuardianUiState.Empty
            1 -> GuardianUiState.OneChild(children.single())
            // The first reachable child is selected, matching the lens's
            // own `child_enrollment_id` so a guardian lands somewhere
            // rather than on a chooser they did not ask for.
            else -> GuardianUiState.SeveralChildren(children, children.first())
        }
    }

    /**
     * Switch to another child, **replacing** the current view.
     *
     * **The whole of [BR4.2, NFR14.30], and it is an absence as much as
     * a behaviour.** This returns a new [GuardianUiState.SeveralChildren]
     * with a different `selected`; it pushes nothing, stacks nothing and
     * records no history. Back therefore cannot reach the previous
     * child's data, because there is no previous destination to go back
     * to — only a previous value of a field that has been overwritten.
     *
     * No server-side control can observe this [NFR23.6]: both requests
     * are legitimately authorized, the lens is correct in both, and
     * neither response is anomalous. The rendering test is the only
     * mechanism, so it is not optional and not a review note.
     *
     * A child not in this guardian's own list is refused rather than
     * selected. The authorization that matters is the server's — every
     * subsequent request names the child as a path parameter and is
     * scoped by the lens [BR4.1] — but selecting a seat this guardian
     * cannot reach would put a child's name on screen before the
     * server ever refused the data behind it.
     *
     * @param state The current several-children state
     * @param child The child to show instead
     * @return The state with that child selected, or a failure
     */
    fun afterChildSelected(
        state: GuardianUiState.SeveralChildren,
        child: GuardianChild,
    ): GuardianUiState {
        if (child !in state.children) {
            return GuardianUiState.Failed(UNEXPECTED_KEY, retryable = false)
        }
        return state.copy(selected = child)
    }

    /**
     * Map a server error envelope.
     *
     * `retryable` is **read from the envelope**, never inferred from a
     * status code [TC-9].
     *
     * @param envelope The server's error
     * @return The state the screen renders
     */
    fun afterError(envelope: ErrorEnvelope): GuardianUiState =
        GuardianUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): GuardianUiState =
        GuardianUiState.Failed(OFFLINE_KEY, retryable = true)

    /**
     * Convert one reachable seat.
     *
     * @param dto The seat the server returned
     * @return The child the screen renders
     */
    private fun toChild(dto: GuardianChildDto): GuardianChild =
        GuardianChild(
            enrollmentId = dto.enrollmentId,
            displayName = dto.displayName,
            batchName = dto.batchName,
            teacherDisplayName = dto.teacherDisplayName,
        )
}
