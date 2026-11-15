package com.shikkhokplus.app.core.model

/**
 * What an edit form did to an optional email field [W7.5, C2].
 *
 * **Three outcomes, because a patch has three.** Left as it was, the
 * field is omitted and the server keeps it; changed, the new value is
 * sent; emptied, JSON `null` is sent and the server clears it. A nullable
 * string cannot say all three: the client's JSON omits nulls, so "clear"
 * would read as "unchanged" and an emptied field would silently stay.
 */
sealed interface EmailEdit {
    /** Left as it was: omitted from the body. */
    data object Unchanged : EmailEdit

    /**
     * Changed to a new address.
     *
     * @property address The address as typed, trimmed when sent
     */
    data class Set(val address: String) : EmailEdit {
        // Someone else's address, typed by a teacher [NFR3.2].
        override fun toString(): String = "Set(address=***)"
    }

    /** Emptied: sent as JSON `null`, which clears it. */
    data object Clear : EmailEdit

    companion object {
        /**
         * Compare what the form holds with what was stored.
         *
         * @param stored The address the server last returned, or null
         * @param typed What the field holds now
         * @return The edit those two describe
         */
        fun of(stored: String?, typed: String): EmailEdit {
            val now = typed.trim()
            val before = stored.orEmpty()
            return when {
                now == before -> Unchanged
                now.isEmpty() -> Clear
                else -> Set(now)
            }
        }
    }
}
