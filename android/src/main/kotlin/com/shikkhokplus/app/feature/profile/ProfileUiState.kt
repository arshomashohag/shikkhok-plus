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
     * @property offline True when this is the copy read earlier in the
     *   session, shown because the latest read could not reach the
     *   server (T9, S4, G4 "Error · offline"). Nothing is stored on the
     *   phone for this: the copy lives only as long as the screen does.
     */
    data class Viewing(
        val selfName: String?,
        val address: String?,
        val phone: String? = null,
        val offline: Boolean = false,
    ) : ProfileUiState

    /**
     * The form is open.
     *
     * @property selfName The name being edited
     * @property address The address being edited, in its four parts
     */
    data class Editing(
        val selfName: String,
        val address: PostalAddress = PostalAddress(),
    ) : ProfileUiState

    /** The save is in flight. */
    data object Saving : ProfileUiState

    /**
     * The save succeeded.
     *
     * @property selfName The saved name
     * @property address The saved address
     * @property phone The sign-in number, unchanged by a save
     */
    data class Saved(
        val selfName: String?,
        val address: String?,
        val phone: String? = null,
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

/**
 * The last profile the server confirmed, kept while the form is open.
 *
 * **Why a second value beside [ProfileUiState].** Edit profile is its
 * own screen (S4) pushed over More, and More stays composed underneath
 * it. While the form is open the state is `Editing` or `Saving`, which
 * carry what is being typed rather than what is stored, so More draws
 * its profile card from this instead. It changes only on a confirmed
 * read or save, never on a keystroke.
 *
 * @property selfName The stored name, or null
 * @property address The stored address on one line, or null
 * @property phone The sign-in number, or null
 * @property postal The stored address in its four parts, for the form
 */
data class ProfileSummary(
    val selfName: String?,
    val address: String?,
    val phone: String?,
    val postal: PostalAddress = PostalAddress(),
)
