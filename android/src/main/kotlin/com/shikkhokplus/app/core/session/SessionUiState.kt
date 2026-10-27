package com.shikkhokplus.app.core.session

/**
 * What the app knows about who is signed in, before it routes.
 *
 * **Four states, because four things can be true**, and collapsing
 * any pair of them produces a wrong screen rather than a slow one:
 *
 * - [Resolving] is not [NoLens]. Treating "still asking" as "nothing
 *   available" is the same defect already fixed once at sign-in,
 *   where `Idle` meant both "never signed in" and "still checking"
 *   and a returning teacher saw a login screen.
 * - [NoLens] is not [Failed]. A fresh signup legitimately holds no
 *   seat until a teacher adds them; telling them to retry would
 *   invite them to retry forever against a correct answer.
 * - [Choosing] is not [Ready]. The server sends no default lens on
 *   purpose [TC-11, D-2], so picking one for a person with two would
 *   be a stored role by another name.
 */
sealed interface SessionUiState {
    /** The lens list is in flight. */
    data object Resolving : SessionUiState

    /**
     * A lens is in use and the app can route.
     *
     * **[fromPicker] is what decides whether "Switch role" appears**,
     * and it has to be carried here because by this point the list is
     * gone: a person who held one lens and a person who chose between
     * two are both simply `Ready`. Offering the picker to the first
     * would send them to a screen that picks for them and returns.
     *
     * @property lens The lens in use
     * @property fromPicker Whether more than one was available
     */
    data class Ready(
        val lens: Lens,
        val fromPicker: Boolean = false,
    ) : SessionUiState

    /**
     * More than one lens; the person picks [TC-11, D-2].
     *
     * @property options Every lens, in the server's order
     */
    data class Choosing(val options: List<LensOption>) : SessionUiState

    /**
     * No lens at all, which is the state of a new account.
     *
     * Reached by anyone who signed themselves up before a teacher
     * recorded their number. Their seat appears the moment it is
     * created, so the app sends them to invitations rather than to an
     * error.
     */
    data object NoLens : SessionUiState

    /**
     * The lens list could not be read.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : SessionUiState
}
