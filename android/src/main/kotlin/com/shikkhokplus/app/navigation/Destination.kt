package com.shikkhokplus.app.navigation

/**
 * Every destination this app can reach, as one closed set.
 *
 * **A sealed hierarchy rather than loose string constants**, so adding
 * a screen without routing it fails to compile rather than producing a
 * route nothing navigates to. That is the failure this file exists to
 * correct: 23 screens were built and 3 were reachable, because the
 * previous navigation was a nullable id in `MainActivity` and nothing
 * made the gap visible.
 *
 * Routes are plain strings because that is what `NavHost` takes. The
 * arguments are built by the `of` helpers rather than by call sites
 * interpolating, so a route and its argument name cannot drift apart.
 */
sealed interface Destination {
    /** The route pattern `NavHost` registers. */
    val route: String

    /** OTP entry. The start destination for a signed-out person. */
    data object Auth : Destination {
        override val route: String = "auth"
    }

    /**
     * Self-registration.
     *
     * **Reachable from [Auth], which is the whole point.** The screen
     * and its state machine shipped in D1; nothing could open it, so a
     * person whose number no teacher had recorded reached a dead end:
     * "a code is on its way if this number is registered", with no way
     * to register.
     */
    data object Signup : Destination {
        override val route: String = "signup"
    }

    /** A teacher's classes. The start destination once signed in. */
    data object Batches : Destination {
        override val route: String = "batches"
    }

    /** The create-a-class form. */
    data object CreateBatch : Destination {
        override val route: String = "batches/new"
    }

    /**
     * One class's roster.
     *
     * The name travels in the route beside the id because the roster
     * endpoint does not return it, and a round trip to re-learn what
     * the teacher just tapped would be the client asking the server
     * something it was already told.
     */
    data object Roster : Destination {
        override val route: String = "batches/{batchId}/roster?name={batchName}"

        /** The id argument's name, used by both the pattern and the reader. */
        const val ARG_ID: String = "batchId"

        /** The name argument's name. */
        const val ARG_NAME: String = "batchName"

        /**
         * Build a concrete route for one class.
         *
         * @param id The batch to open
         * @param name The teacher's name for it, for the title
         * @return The route to navigate to
         */
        fun of(
            id: String,
            name: String,
        ): String = "batches/$id/roster?name=${java.net.URLEncoder.encode(name, "UTF-8")}"
    }

    /** The add-a-student form, scoped to one class. */
    data object AddStudent : Destination {
        override val route: String = "batches/{batchId}/roster/add"

        /**
         * Build a concrete route for one class.
         *
         * @param id The batch to add into
         * @return The route to navigate to
         */
        fun of(id: String): String = "batches/$id/roster/add"
    }
}
