package com.shikkhokplus.app.feature.profile

/**
 * Everything the profile screen renders.
 *
 * **The EDIT half of `O5` only.** The mockups draw four deletion states
 * on this same screen because one screen is where they live, but both
 * account-deletion paths are D6's: they are release-blocking V1
 * deliverables with their own tests [TC-19, RC-4, RC-5], and a
 * half-built deletion flow is worse than none.
 *
 * What a person writes here lands on their own private profile and
 * **changes no teacher's roster** [BR3.1, AC1.5.3]. Each teacher keeps
 * seeing the name that teacher typed, which is answered by which table
 * the server reads rather than by a filter anybody applies.
 */
sealed interface ProfileUiState {
    /** Nothing has been asked for yet. */
    data object Loading : ProfileUiState

    /**
     * The profile, as its owner sees it.
     *
     * @property selfName The name this person chose, or null
     * @property address The address this person entered, or null
     * @property phone The sign-in number, shown read-only (O5)
     */
    data class Viewing(
        val selfName: String?,
        val address: String?,
        val phone: String? = null,
    ) : ProfileUiState

    /**
     * The form is open.
     *
     * @property selfName The name being edited
     * @property address The address being edited
     */
    data class Editing(
        val selfName: String,
        val address: String,
    ) : ProfileUiState

    /** The save is in flight. */
    data object Saving : ProfileUiState

    /**
     * The save succeeded.
     *
     * @property selfName The saved name
     * @property address The saved address
     */
    data class Saved(
        val selfName: String?,
        val address: String?,
    ) : ProfileUiState

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
    ) : ProfileUiState
}
