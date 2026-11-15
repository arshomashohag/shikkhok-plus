package com.shikkhokplus.app.core.session

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MeDto

/**
 * Turns one `GET /v1/me` response into what the app routes on.
 *
 * **This object is the unit under test**, rather than "the
 * ViewModel". Every routing decision is made here, so a test drives
 * it without a dispatcher [TC-9, D-31] — and routing is the one place
 * where a wrong decision sends a person to a screen the server will
 * refuse.
 */
object SessionStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /**
     * Map the lens list the server reported.
     *
     * **The count decides, and all three outcomes are real.** The
     * server sends no default [TC-11, D-2]: one lens means there is
     * nothing to choose, two or more means the person chooses, and
     * none means their teacher has not added them yet — which is an
     * ordinary state for a fresh signup, not a failure.
     *
     * When the server says the account has no username yet, the state
     * is wrapped in [SessionUiState.UsernameRequired] so the
     * choose-username gate comes first [FR5.2].
     *
     * @param dto What the server returned
     * @return Ready, Choosing, or NoLens, wrapped when a username is required
     */
    fun afterLoad(dto: MeDto): SessionUiState {
        val lenses = lensStateOf(dto)
        // **The flag travels inside the state, not beside it** [FR5.2,
        // NFR3.12]. One write carries both facts, so no frame can show
        // the picker or a home before the gate; the state it would have
        // been is kept for the moment a username is chosen.
        return if (dto.usernameRequired) SessionUiState.UsernameRequired(then = lenses) else lenses
    }

    /**
     * The lens state alone, whatever the username flag says.
     *
     * @param dto What the server returned
     * @return Ready, Choosing, or NoLens
     */
    private fun lensStateOf(dto: MeDto): SessionUiState {
        val options = readLenses(dto.lenses)
        return when {
            options.isEmpty() -> SessionUiState.NoLens
            // A single entry is the server's documented cue to skip
            // the picker: asking someone to choose between one thing
            // is a tap that teaches them nothing.
            options.size == 1 -> SessionUiState.Ready(options.single().lens)
            else -> SessionUiState.Choosing(options)
        }
    }

    /**
     * Map a server error envelope.
     *
     * `retryable` is the server's [TC-9]. A client that decided it
     * from the status code would offer a retry into a refusal.
     *
     * @param envelope The envelope the server sent
     * @return The failed state
     */
    fun afterError(envelope: ErrorEnvelope): SessionUiState =
        SessionUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a request that never reached the server.
     *
     * Always retryable: nothing refused it, so there is no server
     * decision to respect.
     *
     * @return The failed state
     */
    fun afterTransportFailure(): SessionUiState =
        SessionUiState.Failed(messageKey = OFFLINE_KEY, retryable = true)
}
