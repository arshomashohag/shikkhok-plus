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

    /** The teacher's day (T1). The start of that lens's tab bar. */
    data object Today : Destination {
        override val route: String = "today"
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

    /** One batch's weekly classes, which sessions are generated from. */
    data object BatchSchedule : Destination {
        override val route: String = "batches/{batchId}/schedule"

        /**
         * Build a concrete route for one batch.
         *
         * @param id The batch
         * @return The route to navigate to
         */
        fun of(id: String): String = "batches/$id/schedule"
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

    /**
     * The create-exam form, scoped to one batch.
     *
     * Nested under [Exams] so the form can share that list's
     * ViewModel: the exam appears in the list the form returns to.
     */
    data object CreateExam : Destination {
        override val route: String = "batches/{batchId}/exams/new"

        /**
         * Build a concrete route for one batch.
         *
         * @param id The batch the exam is for
         * @return The route to navigate to
         */
        fun of(id: String): String = "batches/$id/exams/new"
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

    /**
     * One seat's marks across exams [BR6.6], for the student or a
     * guardian. The heading names travel in the route because the
     * series itself carries none.
     */
    data object Progress : Destination {
        override val route: String =
            "progress/{enrollmentId}?reader={reader}&child={child}&batch={batch}"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "enrollmentId"

        /** The reader argument's name. */
        const val ARG_READER: String = "reader"

        /** Whose series, for the heading. */
        const val ARG_CHILD: String = "child"

        /** Which class, for the heading. */
        const val ARG_BATCH: String = "batch"

        /**
         * Build a concrete route for one seat.
         *
         * @param enrollmentId The seat
         * @param reader `SELF` or `CHILD`
         * @param child Whose series
         * @param batch Which class
         * @return The route to navigate to
         */
        fun of(
            enrollmentId: String,
            reader: String,
            child: String,
            batch: String,
        ): String =
            "progress/$enrollmentId?reader=$reader" +
                "&child=${java.net.URLEncoder.encode(child, "UTF-8")}" +
                "&batch=${java.net.URLEncoder.encode(batch, "UTF-8")}"
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

    /** Payments waiting for the teacher to check (T4). */
    data object Verify : Destination {
        override val route: String = "verify"
    }

    /** The reader's own inbox: fee reminders from their teachers. */
    data object Inbox : Destination {
        override val route: String = "me/notifications"
    }

    /** A student's batches (S1). The start destination for that lens. */
    data object MyBatches : Destination {
        override val route: String = "me/batches"
    }

    /** A child's payments (G3), keyed by one of the child's seats. */
    data object ChildPayments : Destination {
        override val route: String = "children/{seat}/payments"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "seat"

        /**
         * Build a concrete route.
         *
         * @param seat One of the child's seats
         * @return The route to navigate to
         */
        fun of(seat: String): String = "children/$seat/payments"
    }

    /** A child's progress (G2), opened on one seat's batch. */
    data object ChildProgress : Destination {
        override val route: String = "children/{seat}/progress"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "seat"

        /**
         * Build a concrete route.
         *
         * @param seat The seat whose batch to show first
         * @return The route to navigate to
         */
        fun of(seat: String): String = "children/$seat/progress"
    }

    /** Pay for a child (G3's form), opened on one seat's fee. */
    data object ChildPay : Destination {
        override val route: String = "children/{seat}/pay"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "seat"

        /**
         * Build a concrete route.
         *
         * @param seat The seat whose fee to pay
         * @return The route to navigate to
         */
        fun of(seat: String): String = "children/$seat/pay"
    }

    /** Pay a fee (S3), optionally opened on one seat's fee. */
    data object Pay : Destination {
        override val route: String = "me/pay?seat={seat}"

        /** The optional seat argument's name. */
        const val ARG_SEAT: String = "seat"

        /**
         * Build a concrete route.
         *
         * @param enrollmentId The seat to open on, or null to choose
         * @return The route to navigate to
         */
        fun of(enrollmentId: String? = null): String =
            if (enrollmentId == null) "me/pay" else "me/pay?seat=$enrollmentId"
    }

    /** One of the student's batches (S2). */
    data object StudentBatch : Destination {
        override val route: String = "me/batches/{enrollmentId}"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "enrollmentId"

        /**
         * Build a concrete route for one seat.
         *
         * @param enrollmentId The student's own seat
         * @return The route to navigate to
         */
        fun of(enrollmentId: String): String = "me/batches/$enrollmentId"
    }

    /** A guardian's children. The start destination for that lens. */
    data object GuardianHome : Destination {
        override val route: String = "children"
    }

    /** Seats awaiting acceptance [BR1.4]. */
    data object Invitations : Destination {
        override val route: String = "invitations"
    }

    /** Deleting one's own account (O5) [TC-19]. */
    data object DeleteAccount : Destination {
        override val route: String = "profile/delete"
    }

    /** The signed-in person's own profile. The More tab. */
    data object Profile : Destination {
        override val route: String = "profile"
    }
}
