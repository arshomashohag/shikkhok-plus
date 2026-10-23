package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.core.network.AlreadyAddedDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.SignupResponseDto

/**
 * Maps signup responses to a [SignupUiState].
 *
 * **This object is the unit under test**, rather than "the ViewModel".
 * It is pure: no network, no storage, no clock.
 */
object SignupStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be understood. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /** The key shown beside a number field that is not a number. */
    const val PHONE_KEY: String = "signup.phone.invalid"

    /** The key shown beside an empty name field. */
    const val NAME_KEY: String = "signup.name.required"

    /**
     * Map the already-added lookup.
     *
     * **Three outcomes and no fourth.** A number with no seat gives
     * the empty form; a number with one gives a pre-filled, role-locked
     * form; and a response claiming a seat without the name or role to
     * fill it is a failure rather than a half-locked form, because
     * locking the role to a guess is worse than not locking it
     * [BR4.5].
     *
     * @param dto The lookup's answer
     * @return The state the screen renders
     */
    fun afterLookup(dto: AlreadyAddedDto): SignupUiState {
        if (!dto.alreadyAdded) {
            return SignupUiState.Empty
        }

        val role = SignupRole.fromWire(dto.role)
        val name = dto.displayName
        if (role == null || name == null) {
            return SignupUiState.Failed(UNEXPECTED_KEY, retryable = false)
        }
        return SignupUiState.AlreadyAdded(prefilledName = name, lockedRole = role)
    }

    /**
     * Check the form's shape before submitting it.
     *
     * **Format only, never policy** [team: Layer boundaries]. This
     * checks that a number looks like a number and a name is not
     * blank. It does not check whether the number already has an
     * account, which is a server decision -- duplicating it here is
     * the validation-divergence erosion path, and the client's copy
     * would be the one that went stale.
     *
     * The address is not validated at all: Bangladesh addresses do not
     * decompose cleanly, and a format rule would reject real ones.
     *
     * @param phone The typed number
     * @param selfName The typed name
     * @return [SignupUiState.Invalid] with a key per bad field, or null
     *   when the form may be submitted
     */
    fun validate(
        phone: String,
        selfName: String,
    ): SignupUiState.Invalid? {
        val problems = mutableListOf<String>()
        if (phone.length !in MIN_PHONE..MAX_PHONE || !phone.any { it.isDigit() }) {
            problems.add(PHONE_KEY)
        }
        if (selfName.isBlank()) {
            problems.add(NAME_KEY)
        }
        return if (problems.isEmpty()) null else SignupUiState.Invalid(problems)
    }

    /**
     * Map a successful signup.
     *
     * @param dto The server's answer
     * @return The code-sent state, naming the destination
     */
    fun afterSignup(dto: SignupResponseDto): SignupUiState =
        SignupUiState.CodeSent(dto.codeSentTo)

    /**
     * Map a server error envelope.
     *
     * The number-already-registered refusal arrives through here like
     * any other: the server names the string and says whether a retry
     * would help [BR4.4, TC-9].
     *
     * @param envelope The server's error
     * @return The state the screen renders
     */
    fun afterError(envelope: ErrorEnvelope): SignupUiState =
        SignupUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): SignupUiState =
        SignupUiState.Failed(OFFLINE_KEY, retryable = true)

    /** The shortest number the API accepts. */
    private const val MIN_PHONE = 8

    /** The longest number the API accepts. */
    private const val MAX_PHONE = 20
}
