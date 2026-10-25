package com.shikkhokplus.app.core.model

/**
 * What a person says they are when they sign up.
 *
 * A **claim**, not a stored role [BR4.2]. Nothing verifies it, and the
 * app stores nothing about it: the lens a person holds is resolved by
 * the server on every request from owned batches and accepted seats
 * [TC-11, D-2], so this value exists only long enough to be submitted.
 *
 * `wire` is the exact token the API expects. Spelled here rather than
 * derived from `name.lowercase()`, because a derivation makes the
 * contract depend on a Kotlin identifier that a rename would silently
 * change.
 *
 * @property wire The value the API carries
 */
enum class SignupRole(val wire: String) {
    /** Creates an `Owner` row on the server, and only this one does. */
    TEACHER("teacher"),

    /** Carries no server-side consequence of its own. */
    STUDENT("student"),

    /** Carries no server-side consequence of its own. */
    GUARDIAN("guardian"),

    ;

    companion object {
        /**
         * Read a role from the wire token the server sent.
         *
         * Returns null for an unknown token rather than defaulting,
         * because the already-added path **locks** the form to this
         * value [BR4.5] -- and a wrong lock is worse than an unlocked
         * form. The caller surfaces the failure.
         *
         * @param wire The token the server sent
         * @return The matching role, or null
         */
        fun fromWire(wire: String?): SignupRole? = entries.firstOrNull { it.wire == wire }
    }
}

/**
 * Whether the holder of a link has answered its invitation.
 *
 * **Per link, never per seat** [BR5.2]. One enrollment carries two of
 * these -- one for the student and one for the guardian -- and one
 * person's answer never speaks for the other.
 *
 * Only [PENDING] and [DECLINED] ever reach this app's invitation
 * screens, because an accepted link resolves no invitation lens at all
 * [BR1.3]. [ACCEPTED] exists because the decision response reports it
 * back after an accept.
 *
 * **[DECLINED] is not terminal** [BR5.4]. A decline is durable against
 * the teacher and reversible by its holder at any time, so a declined
 * seat stays listed with an accept action [AC1.13.1] -- and a UI that
 * treated this as an end state would turn a mis-tap into a permanent
 * lockout from somebody's own records.
 *
 * @property wire The value the API carries
 */
enum class AcceptanceState(val wire: String) {
    /** Created by a teacher and not yet answered. */
    PENDING("pending"),

    /** Answered yes; the matching lens is granted. */
    ACCEPTED("accepted"),

    /** Answered no, reversibly. */
    DECLINED("declined"),

    ;

    companion object {
        /**
         * Read a state from the wire token the server sent.
         *
         * Returns null for an unknown token rather than defaulting to
         * [PENDING], which would render a declined seat as if it had
         * never been answered. The mapper turns null into an explicit
         * failure state [RosterStateMapper's rule, applied here].
         *
         * @param wire The token the server sent
         * @return The matching state, or null
         */
        fun fromWire(wire: String?): AcceptanceState? =
            entries.firstOrNull { it.wire == wire }
    }
}

/**
 * The state of one link on a seat, as the teacher's roster reports it.
 *
 * **Four values where [AcceptanceState] has three**, and the fourth is
 * the point: a seat with no guardian recorded has no decision to report
 * [BR2.2]. Answering [PENDING] there would count a decision nobody was
 * asked for as outstanding, making the batch's figure wrong by exactly
 * the number of guardian-less seats.
 *
 * A separate type rather than a nullable [AcceptanceState] for the same
 * reason the server sends a fourth VALUE rather than a null: a `when`
 * over this fails to compile if a fifth state ever appears, where a
 * null silently takes whichever branch handles it.
 *
 * [ABSENT] reaches the guardian link only. A seat always has a student
 * link — that is what the seat IS — so a student reporting absent is a
 * contract failure, which is why the mapper refuses it rather than
 * rendering it.
 *
 * @property wire The value the API carries
 */
enum class LinkState(val wire: String) {
    /** Recorded and not yet answered. The NORMAL state of a new seat. */
    PENDING("pending"),

    /** Answered yes; this link's holder holds a lens over the seat. */
    ACCEPTED("accepted"),

    /** Answered no, reversibly by its holder [BR5.4]. */
    DECLINED("declined"),

    /** No such link exists. Not a decision, and not an outstanding one. */
    ABSENT("absent"),

    ;

    companion object {
        /**
         * Read a link state from the wire token the server sent.
         *
         * Returns null for an unknown token rather than defaulting,
         * because every default here is a lie about somebody's answer:
         * rendering a declined seat as pending invites a teacher to
         * wait for an answer that has already arrived. The mapper turns
         * null into an explicit failure state.
         *
         * @param wire The token the server sent
         * @return The matching state, or null
         */
        fun fromWire(wire: String?): LinkState? = entries.firstOrNull { it.wire == wire }
    }
}
