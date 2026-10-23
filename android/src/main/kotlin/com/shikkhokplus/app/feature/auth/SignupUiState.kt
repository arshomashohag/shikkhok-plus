package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.model.SignupRole

/**
 * Everything the signup screen renders, decided here.
 *
 * `O1` draws five states and each is one of these. A composable
 * receives one and renders it with no conditionals depending on a
 * domain value [TC-9, D-31].
 */
sealed interface SignupUiState {
    /** The empty form. No number has been looked up yet. */
    data object Empty : SignupUiState

    /** The lookup is in flight. */
    data object CheckingNumber : SignupUiState

    /**
     * A teacher already added this number.
     *
     * **The name is pre-filled and correctable, and the role is
     * locked** [BR4.5, AC1.12.1]. The screen also states that a
     * teacher added this number and names **neither the teacher nor
     * the batch** [AC1.12.2] -- which this state can honour because it
     * holds neither value to render.
     *
     * @property prefilledName The teacher-typed name, correctable
     * @property lockedRole The role the seat carries
     */
    data class AlreadyAdded(
        val prefilledName: String,
        val lockedRole: SignupRole,
    ) : SignupUiState

    /**
     * The form has a problem the person can fix without the server.
     *
     * **Format only, never policy** [team: Layer boundaries]. A
     * duplicate number is not here: whether a number already has an
     * account is a server decision and arrives as [Failed].
     *
     * @property fieldKeys A string resource key per offending field
     */
    data class Invalid(val fieldKeys: List<String>) : SignupUiState

    /** The signup is in flight. */
    data object Submitting : SignupUiState

    /**
     * The account exists and a code is on its way.
     *
     * Carries the destination so the screen can name the number the
     * code went to [BR4.3, AC1.11.4].
     *
     * @property codeSentTo The number the code was sent to
     */
    data class CodeSent(val codeSentTo: String) : SignupUiState

    /**
     * Something failed, and the screen can say what to do about it.
     *
     * The number-already-registered case arrives here with
     * `signup.number.already_registered`, which the screen renders
     * alongside a path to log in [BR4.4, AC1.12.4, `O1` state 5].
     *
     * @property messageKey Names a string resource; never English text
     *   from the server, which could not be localized [TC-15, D-43]
     * @property retryable Read from the server's envelope, never
     *   inferred from a status code [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : SignupUiState
}
