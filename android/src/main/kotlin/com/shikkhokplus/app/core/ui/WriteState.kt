package com.shikkhokplus.app.core.ui

/**
 * Where a form's write stands, separately from the list it changes.
 *
 * **Separate from the list's state, and that separation is the fix.**
 * Both create forms used to call the write and navigate away in the
 * same tap. The list then re-entered composition and reloaded, so two
 * coroutines wrote one state and the last response won. A refused
 * create followed by a slower list read left the teacher looking at
 * their old list with no error: the class was never created and
 * nothing said so.
 *
 * Holding the write's outcome here lets the form stay open until the
 * server has answered. It closes on [Saved] and only then; on [Failed]
 * it stays open, with what the person typed still in the fields.
 */
sealed interface WriteState {
    /** Nothing in flight. */
    data object Idle : WriteState

    /** The request is in flight; the form must not submit again. */
    data object Saving : WriteState

    /** The server accepted it. The form closes, once. */
    data object Saved : WriteState

    /**
     * The server refused it, or never answered.
     *
     * @property messageKey Names a string resource [TC-15, D-43]
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : WriteState
}
