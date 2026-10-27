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

    /** Today's summary. The first tab. */
    data object Overview : Destination {
        override val route: String = "overview"
    }

    /** A teacher's classes. The start destination once signed in. */
    data object Batches : Destination {
        override val route: String = "batches"
    }

    /** Who owes money, across every batch. The third tab. */
    data object Dues : Destination {
        override val route: String = "dues"
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

    /**
     * One class's sessions, for attendance and the topic log.
     *
     * The name travels beside the id for the same reason [Roster]
     * does: the sessions endpoint does not return it.
     */
    data object Sessions : Destination {
        override val route: String = "batches/{batchId}/sessions?name={batchName}"

        /**
         * Build a concrete route for one class.
         *
         * @param id The batch to open
         * @param name The teacher's name for it
         * @return The route to navigate to
         */
        fun of(
            id: String,
            name: String,
        ): String =
            "batches/$id/sessions?name=" +
                java.net.URLEncoder.encode(name, "UTF-8")
    }

    /** Marking one session's roster [BR3.5]. */
    data object Attendance : Destination {
        override val route: String = "sessions/{sessionId}/attendance"

        /** The session argument's name. */
        const val ARG_SESSION: String = "sessionId"

        /**
         * Build a concrete route for one session.
         *
         * @param sessionId The session to mark
         * @return The route to navigate to
         */
        fun of(sessionId: String): String = "sessions/$sessionId/attendance"
    }

    /** One class's exams. */
    data object Exams : Destination {
        override val route: String = "batches/{batchId}/exams?name={batchName}"

        /**
         * Build a concrete route for one class.
         *
         * @param id The batch to open
         * @param name The teacher's name for it
         * @return The route to navigate to
         */
        fun of(
            id: String,
            name: String,
        ): String =
            "batches/$id/exams?name=" +
                java.net.URLEncoder.encode(name, "UTF-8")
    }

    /** Entering one exam's marks [BR4.2]. */
    data object MarkEntry : Destination {
        override val route: String = "exams/{examId}/marks"

        /** The exam argument's name. */
        const val ARG_EXAM: String = "examId"

        /**
         * Build a concrete route for one exam.
         *
         * @param examId The exam to mark
         * @return The route to navigate to
         */
        fun of(examId: String): String = "exams/$examId/marks"
    }

    /**
     * One seat's marksheet [BR6.2].
     *
     * **The reader is in the route**, because a student and a guardian
     * read the same seat over two different server paths, each
     * resolving its own lens [BR7.2]. Carrying it here keeps the
     * screen from guessing which it is.
     */
    data object Marksheet : Destination {
        override val route: String =
            "marksheet/{examId}/{enrollmentId}?reader={reader}"

        /** The exam argument's name. */
        const val ARG_EXAM: String = "examId"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "enrollmentId"

        /** The reader argument's name. */
        const val ARG_READER: String = "reader"

        /**
         * Build a concrete route for one seat's marksheet.
         *
         * @param examId The exam
         * @param enrollmentId The seat
         * @param reader `SELF` or `CHILD`
         * @return The route to navigate to
         */
        fun of(
            examId: String,
            enrollmentId: String,
            reader: String,
        ): String = "marksheet/$examId/$enrollmentId?reader=$reader"
    }

    /** A child's marks across exams [BR6.6]. */
    data object Progress : Destination {
        override val route: String = "children/{enrollmentId}/progress"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "enrollmentId"

        /**
         * Build a concrete route for one child.
         *
         * @param enrollmentId The child's seat
         * @return The route to navigate to
         */
        fun of(enrollmentId: String): String = "children/$enrollmentId/progress"
    }

    /**
     * One seat's fee history.
     *
     * **The reader is in the route** for the same reason [Marksheet]
     * carries one: three lenses read this through three server paths,
     * and the screen must not pick for itself.
     */
    data object FeeHistory : Destination {
        override val route: String = "fees/{enrollmentId}?reader={reader}"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "enrollmentId"

        /** The reader argument's name. */
        const val ARG_READER: String = "reader"

        /**
         * Build a concrete route for one seat.
         *
         * @param enrollmentId The seat
         * @param reader `STUDENT`, `GUARDIAN` or `TEACHER`
         * @return The route to navigate to
         */
        fun of(
            enrollmentId: String,
            reader: String,
        ): String = "fees/$enrollmentId?reader=$reader"
    }

    /** A guardian's children. The start destination for that lens. */
    data object GuardianHome : Destination {
        override val route: String = "children"
    }

    /** Seats awaiting acceptance [BR1.4]. */
    data object Invitations : Destination {
        override val route: String = "invitations"
    }

    /** The signed-in person's own profile. The More tab. */
    data object Profile : Destination {
        override val route: String = "profile"
    }
}
