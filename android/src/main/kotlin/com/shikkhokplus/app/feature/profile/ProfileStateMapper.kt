package com.shikkhokplus.app.feature.profile

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MeDto

/**
 * Turns one profile response into what the screen renders.
 *
 * **This object is the unit under test**, rather than "the
 * ViewModel". Every decision the screen depends on is made here, so a
 * test drives it without a dispatcher [TC-9, D-31].
 */
object ProfileStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /**
     * Map a profile that was read.
     *
     * **A null name is a real state, not a failure.** A person whose
     * teacher recorded only their number has no profile row until
     * they register; showing the form empty is the honest answer, and
     * treating it as an error would make an ordinary first visit look
     * broken.
     *
     * @param dto What the server returned
     * @return The viewing state
     */
    fun afterLoad(dto: MeDto): ProfileUiState =
        ProfileUiState.Viewing(selfName = dto.selfName, address = dto.address)

    /**
     * Map a successful save.
     *
     * Distinct from [afterLoad] because the screen says something
     * after a save that it does not say after a read.
     *
     * @param dto What the server returned
     * @return The saved state
     */
    fun afterSave(dto: MeDto): ProfileUiState =
        ProfileUiState.Saved(selfName = dto.selfName, address = dto.address)

    /**
     * Map a server error envelope.
     *
     * The client decides neither the message nor whether a retry
     * would help: the server names the string and states the
     * retryability [TC-9].
     *
     * @param envelope The server's error
     * @return The failure state
     */
    fun afterError(envelope: ErrorEnvelope): ProfileUiState =
        ProfileUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * @return The offline state, which is retryable
     */
    fun afterTransportFailure(): ProfileUiState =
        ProfileUiState.Failed(OFFLINE_KEY, retryable = true)
}
