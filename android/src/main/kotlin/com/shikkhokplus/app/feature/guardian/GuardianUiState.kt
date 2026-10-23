package com.shikkhokplus.app.feature.guardian

/**
 * One child a guardian can reach, as the screen renders it.
 *
 * **Reached through this guardian's own link, never through the child**
 * [BR4.1, NFR14.29]. The query that produces these rows scopes on
 * `guardian_account_id`; resolving by child and then that child's
 * enrollments would show a guardian recorded by teacher A the batch
 * teacher B keeps for the same child — two teachers' records merged.
 *
 * `batchName` is carried even in the single-child case [AC2.8.5],
 * because that is where attribution is most needed: there is no
 * selection list to have shown it.
 *
 * @property enrollmentId The seat, which every subsequent request names
 *   as a **path parameter** rather than a client-supplied hint
 * @property displayName The teacher-typed name for the child
 * @property batchName Which class
 * @property teacherDisplayName Which teacher recorded this, if named
 */
data class GuardianChild(
    val enrollmentId: String,
    val displayName: String,
    val batchName: String,
    val teacherDisplayName: String?,
)

/**
 * Everything the guardian's home screen renders.
 *
 * **[OneChild] and [SeveralChildren] are separate states** rather than
 * a list whose length the screen checks — the same rule that makes
 * `Empty` separate from a `Loaded` with no rows. A composable writing
 * `if (children.size > 1)` would be deciding whether a switcher is
 * needed, which is a decision and belongs in the mapper. The
 * single-child case is also the common one and goes straight through
 * with no switcher drawn at all.
 */
sealed interface GuardianUiState {
    /** Nothing has been asked for yet. */
    data object Idle : GuardianUiState

    /** A request is in flight. */
    data object Loading : GuardianUiState

    /**
     * This guardian reaches exactly one child.
     *
     * The switcher is **not drawn**: there is nothing to switch
     * between, and a control offering one option is noise.
     *
     * @property child The one reachable seat
     */
    data class OneChild(val child: GuardianChild) : GuardianUiState

    /**
     * This guardian reaches more than one child.
     *
     * @property children Every reachable seat, in the server's order
     * @property selected The child currently being shown.
     *
     *   **Selection, not navigation** [BR4.2, NFR14.30, AC9.4.2].
     *   Switching child REPLACES this value within one screen; it never
     *   pushes a destination. That is what makes Back unable to reach
     *   the previous child's data — a privacy case wearing navigation's
     *   clothes, and the one back-stack obligation in D2 worth testing
     *   rather than assuming.
     */
    data class SeveralChildren(
        val children: List<GuardianChild>,
        val selected: GuardianChild,
    ) : GuardianUiState

    /**
     * This guardian reaches nothing.
     *
     * A separate state rather than an empty list, because "nothing to
     * show yet" needs an explanation and a blank screen gives none. A
     * declined guardian link lands here: the seat stays in that
     * guardian's invitations, where they may still accept it [BR5.4].
     */
    data object Empty : GuardianUiState

    /**
     * Something failed.
     *
     * @property messageKey Names a string resource, never English text
     *   from the server [TC-15, D-43]
     * @property retryable Read from the envelope, never inferred [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : GuardianUiState
}
