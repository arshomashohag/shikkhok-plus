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

    /** The teacher's students, apart from any batch [0018]. A tab. */
    data object Students : Destination {
        override val route: String = "students"
    }

    /**
     * The add-a-student form, optionally with one batch already chosen.
     *
     * Opened from the Students tab with no batch, and from a roster's
     * "New student" with that roster's batch chosen.
     */
    data object NewStudent : Destination {
        override val route: String = "students-add?batch={batchId}"

        /** The optional batch argument's name. */
        const val ARG_BATCH: String = "batchId"

        /**
         * Build a concrete route.
         *
         * @param batchId A batch to start chosen, or null for none
         * @return The route to navigate to
         */
        fun of(batchId: String? = null): String = if (batchId == null) "students-add" else "students-add?batch=$batchId"
    }

    /** One of the teacher's students, with every batch they sit in. */
    data object StudentDetail : Destination {
        override val route: String = "students/{studentId}"

        /** The student argument's name. */
        const val ARG_ID: String = "studentId"

        /**
         * Build a concrete route for one student.
         *
         * @param studentId The student
         * @return The route to navigate to
         */
        fun of(studentId: String): String = "students/$studentId"
    }

    /**
     * A roster's "add students": existing students not in this batch,
     * with "New student" for anyone not on the list yet.
     */
    data object PickStudents : Destination {
        override val route: String = "batches/{batchId}/students/pick?name={batchName}"

        /** The batch argument's name. */
        const val ARG_ID: String = "batchId"

        /** The batch name argument's name, for the title. */
        const val ARG_NAME: String = "batchName"

        /**
         * Build a concrete route for one batch.
         *
         * @param id The batch
         * @param name Its name, for the title
         * @return The route to navigate to
         */
        fun of(
            id: String,
            name: String,
        ): String = "batches/$id/students/pick?name=${java.net.URLEncoder.encode(name, "UTF-8")}"
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

    /** A batch's exam and other fees, opened from the batch's header. */
    data object ExtraFees : Destination {
        override val route: String = "batches/{batchId}/extra-fees"

        /** The batch argument's name. */
        const val ARG_BATCH: String = "batchId"

        /**
         * Build a concrete route for one batch.
         *
         * @param batchId The batch
         * @return The route to navigate to
         */
        fun of(batchId: String): String = "batches/$batchId/extra-fees"
    }

    /** Raising an exam or other fee on a batch. */
    data object RaiseExtraFee : Destination {
        override val route: String = "batches/{batchId}/extra-fees/new"

        /** The batch argument's name. */
        const val ARG_BATCH: String = "batchId"

        /**
         * Build a concrete route for one batch.
         *
         * @param batchId The batch
         * @return The route to navigate to
         */
        fun of(batchId: String): String = "batches/$batchId/extra-fees/new"
    }

    /** One exam or other fee and its students. */
    data object ExtraFeeDetail : Destination {
        override val route: String = "extra-fees/{extraFeeId}"

        /** The fee argument's name. */
        const val ARG_FEE: String = "extraFeeId"

        /**
         * Build a concrete route for one fee.
         *
         * @param extraFeeId The fee
         * @return The route to navigate to
         */
        fun of(extraFeeId: String): String = "extra-fees/$extraFeeId"
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
        override val route: String = "fees/{enrollmentId}?reader={reader}&child={child}&batch={batch}"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "enrollmentId"

        /** The reader argument's name. */
        const val ARG_READER: String = "reader"

        /** Whose fees, carried on to the progress dashboard's heading. */
        const val ARG_CHILD: String = "child"

        /** Which class, carried on to the progress dashboard's heading. */
        const val ARG_BATCH: String = "batch"

        /**
         * Build a concrete route for one seat.
         *
         * @param enrollmentId The seat
         * @param reader `STUDENT`, `GUARDIAN` or `TEACHER`
         * @param child Whose fees, or empty
         * @param batch Which class, or empty
         * @return The route to navigate to
         */
        fun of(
            enrollmentId: String,
            reader: String,
            child: String = "",
            batch: String = "",
        ): String =
            "fees/$enrollmentId?reader=$reader" +
                "&child=${java.net.URLEncoder.encode(child, "UTF-8")}" +
                "&batch=${java.net.URLEncoder.encode(batch, "UTF-8")}"
    }

    /**
     * One seat's progress dashboard (D1, D2), for all three readers.
     *
     * **The reader is in the route** because a teacher, a student and a
     * guardian read it over three server paths, each resolving its own
     * lens. The names travel beside the seat because the dashboard
     * response carries none.
     */
    data object Dashboard : Destination {
        override val route: String = "dashboard/{seat}?reader={reader}&child={child}&batch={batch}"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "seat"

        /** The reader argument's name. */
        const val ARG_READER: String = "reader"

        /** Whose progress, for the heading. */
        const val ARG_CHILD: String = "child"

        /** Which class, for the heading. */
        const val ARG_BATCH: String = "batch"

        /**
         * Build a concrete route.
         *
         * @param seat The seat
         * @param reader `TEACHER`, `STUDENT` or `GUARDIAN`
         * @param child Whose progress, or empty
         * @param batch Which class, or empty
         * @return The route to navigate to
         */
        fun of(
            seat: String,
            reader: String,
            child: String = "",
            batch: String = "",
        ): String =
            "dashboard/$seat?reader=$reader" +
                "&child=${java.net.URLEncoder.encode(child, "UTF-8")}" +
                "&batch=${java.net.URLEncoder.encode(batch, "UTF-8")}"
    }

    /** Payments waiting for the teacher to check (T4). */
    data object Verify : Destination {
        override val route: String = "verify"
    }

    /** One payment under review, or already decided (R2 to R4). */
    data object PaymentReview : Destination {
        override val route: String = "verify/{submissionId}"

        /** The payment argument's name. */
        const val ARG_ID: String = "submissionId"

        /**
         * Build a concrete route.
         *
         * @param submissionId The payment
         * @return The route to navigate to
         */
        fun of(submissionId: String): String = "verify/$submissionId"
    }

    /** The reader's own inbox: fee reminders from their teachers. */
    data object Inbox : Destination {
        override val route: String = "me/notifications"
    }

    /**
     * One inbox item opened to its detail.
     *
     * Its own destination so its back arrow pops to [Inbox].
     */
    data object InboxDetail : Destination {
        override val route: String = "inbox/{notificationId}"

        /** The message argument's name. */
        const val ARG_ID: String = "notificationId"

        /**
         * Build a concrete route.
         *
         * @param id The message
         * @return The route to navigate to
         */
        fun of(id: String): String = "inbox/$id"
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

    /** One child's batch, from the guardian's side. */
    data object ChildBatch : Destination {
        override val route: String = "children/{seat}/batch"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "seat"

        /**
         * Build a concrete route.
         *
         * @param seat The child's seat in the batch
         * @return The route to navigate to
         */
        fun of(seat: String): String = "children/$seat/batch"
    }

    /** A past class's detail, opened from a family batch screen. */
    data object FamilyClass : Destination {
        override val route: String = "family/{reader}/{seat}/class/{id}?month={month}"

        /** The reader argument's name. */
        const val ARG_READER: String = "reader"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "seat"

        /** The item argument's name. */
        const val ARG_ID: String = "id"

        /** The month argument's name: `YYYY-MM`, empty when unknown. */
        const val ARG_MONTH: String = "month"

        /**
         * Build a concrete route.
         *
         * @param reader `SELF` or `GUARDIAN`
         * @param seat The seat
         * @param id The class's session id
         * @param month The class's month, `YYYY-MM`, so the detail can
         *   load it after process death
         * @return The route to navigate to
         */
        fun of(reader: String, seat: String, id: String, month: String = ""): String =
            "family/$reader/$seat/class/$id?month=$month"
    }

    /** An upcoming exam's detail, opened from a family batch screen. */
    data object FamilyExam : Destination {
        override val route: String = "family/{reader}/{seat}/exam/{id}"

        /** The reader argument's name. */
        const val ARG_READER: String = "reader"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "seat"

        /** The item argument's name. */
        const val ARG_ID: String = "id"

        /**
         * Build a concrete route.
         *
         * @param reader `SELF` or `GUARDIAN`
         * @param seat The seat
         * @param id The exam
         * @return The route to navigate to
         */
        fun of(reader: String, seat: String, id: String): String = "family/$reader/$seat/exam/$id"
    }

    /** A notice's detail, opened from a family batch screen. */
    data object FamilyNotice : Destination {
        override val route: String = "family/{reader}/{seat}/notice/{id}"

        /** The reader argument's name. */
        const val ARG_READER: String = "reader"

        /** The seat argument's name. */
        const val ARG_SEAT: String = "seat"

        /** The item argument's name. */
        const val ARG_ID: String = "id"

        /**
         * Build a concrete route.
         *
         * @param reader `SELF` or `GUARDIAN`
         * @param seat The seat
         * @param id The notice
         * @return The route to navigate to
         */
        fun of(reader: String, seat: String, id: String): String = "family/$reader/$seat/notice/$id"
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

    /** The teacher's payment methods (P1), opened from More. */
    data object PaymentMethods : Destination {
        override val route: String = "payment-methods"
    }

    /** Adding a payment method (P2, P3). */
    data object AddPaymentMethod : Destination {
        override val route: String = "payment-methods/new?kind={kind}"

        /** The kind argument's name. */
        const val ARG_KIND: String = "kind"

        /**
         * Build a concrete route.
         *
         * @param kind `mobile` or `bank`
         * @return The route to navigate to
         */
        fun of(kind: String): String = "payment-methods/new?kind=$kind"
    }

    /** Editing one payment method. */
    data object EditPaymentMethod : Destination {
        override val route: String = "payment-methods/{methodId}/edit"

        /** The method argument's name. */
        const val ARG_METHOD: String = "methodId"

        /**
         * Build a concrete route.
         *
         * @param methodId The method to edit
         * @return The route to navigate to
         */
        fun of(methodId: String): String = "payment-methods/$methodId/edit"
    }

    /** Collected versus charged, by month (M1), opened from More. */
    data object Collections : Destination {
        override val route: String = "collections"
    }

    /** One month's expenses, opened from More. */
    data object Expenses : Destination {
        override val route: String = "expenses"
    }

    /** Recording an expense. */
    data object RecordExpense : Destination {
        override val route: String = "expenses/new"
    }

    /** The month's money in and out, opened from More. */
    data object MoneySummary : Destination {
        override val route: String = "money-summary"
    }

    /** Opening a coaching centre, from More. */
    data object OpenCentre : Destination {
        override val route: String = "centres/new"
    }

    /** The chosen centre's members, for its managers. */
    data object CentreMembers : Destination {
        override val route: String = "centre/members"
    }

    /** The chosen centre's timetable, for its managers. */
    data object CentreTimetable : Destination {
        override val route: String = "centre/timetable"
    }

    /** A centre teacher's assigned classes, a week at a time. */
    data object MyClasses : Destination {
        override val route: String = "me/classes"
    }

    /** One assigned class: its roster's attendance and its topic. */
    data object MyClass : Destination {
        override val route: String = "me/classes/{sessionId}"

        /** The class argument's name. */
        const val ARG_SESSION: String = "sessionId"

        /**
         * Build a concrete route.
         *
         * @param sessionId The class
         * @return The route to navigate to
         */
        fun of(sessionId: String): String = "me/classes/$sessionId"
    }

    /** The exams a centre asked me to mark. */
    data object MyExams : Destination {
        override val route: String = "me/exams"
    }

    /** One exam's marks, as its examiner enters them. */
    data object MyExamMarks : Destination {
        override val route: String = "me/exams/{examId}"

        /** The exam argument's name. */
        const val ARG_EXAM: String = "examId"

        /**
         * Build a concrete route.
         *
         * @param examId The exam
         * @return The route to navigate to
         */
        fun of(examId: String): String = "me/exams/$examId"
    }

    /** The chosen centre's payroll, for its managers. */
    data object CentrePayroll : Destination {
        override val route: String = "centre/payroll"
    }

    /** My own approved pay, at every centre. */
    data object MyPay : Destination {
        override val route: String = "me/pay"
    }

    /** The chosen centre's rooms. */
    data object CentreRooms : Destination {
        override val route: String = "centre/rooms"
    }

    /** The chosen centre's teachers and staff, for its managers. */
    data object CentreStaff : Destination {
        override val route: String = "centre/staff"
    }

    /** Inviting a teacher to the chosen centre. */
    data object InviteStaffTeacher : Destination {
        override val route: String = "centre/staff/teachers/new"
    }

    /** Adding someone who works at the chosen centre without app access. */
    data object AddOtherStaff : Destination {
        override val route: String = "centre/staff/new"
    }

    /** Correcting one staff record. */
    data object EditStaff : Destination {
        override val route: String = "centre/staff/{staffId}/edit"

        /** The record argument's name. */
        const val ARG_STAFF: String = "staffId"

        /**
         * Build a concrete route.
         *
         * @param staffId The record
         * @return The route to navigate to
         */
        fun of(staffId: String): String = "centre/staff/$staffId/edit"
    }

    /** The coaching centres' offers to this account, from a teacher's More. */
    data object CentreOffers : Destination {
        override val route: String = "centre-offers"
    }

    /** One batch in one month (M2). */
    data object BatchMonth : Destination {
        override val route: String = "batches/{batchId}/month?period={period}&name={batchName}"

        /** The batch argument's name. */
        const val ARG_ID: String = "batchId"

        /** The month argument's name. */
        const val ARG_PERIOD: String = "period"

        /** The batch-name argument's name. */
        const val ARG_NAME: String = "batchName"

        /**
         * Build a concrete route.
         *
         * @param id The batch
         * @param name Its name, carried because the fees read omits it
         * @param period `YYYY-MM`, or null for the current month
         * @return The route to navigate to
         */
        fun of(
            id: String,
            name: String,
            period: String?,
        ): String =
            "batches/$id/month?period=${period.orEmpty()}&name=" +
                java.net.URLEncoder.encode(name, "UTF-8")
    }

    /** The signed-in person's own profile. The More tab. */
    data object Profile : Destination {
        override val route: String = "profile"
    }

    /** Settings: notifications, theme and text size, pushed over More. */
    data object Settings : Destination {
        override val route: String = "settings"
    }

    /** Edit profile (S4), pushed over More. */
    data object EditProfile : Destination {
        override val route: String = "profile/edit"
    }

    /** A guardian's children (G4), pushed over More. */
    data object MyChildren : Destination {
        override val route: String = "profile/children"
    }
}
