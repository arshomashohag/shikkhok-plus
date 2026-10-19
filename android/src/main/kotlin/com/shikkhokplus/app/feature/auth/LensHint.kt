package com.shikkhokplus.app.feature.auth

/**
 * The lens switcher sends a hint. It decides nothing.
 *
 * [D-2] allows a client lens hint for **UI shaping** and forbids
 * trusting it for authorization. The distinction is easy to erode, so
 * it is stated here as a property of the type:
 *
 * * the hint travels **out**, in a header, to say which lens the user
 *   picked from the ones the server already told them they have;
 * * nothing travels **in** on the strength of it — the server response
 *   is self-describing and names the lens that produced it, and the
 *   client renders from the response rather than from the hint it sent.
 *
 * A hint naming a lens the account's data does not support is refused
 * by the server with `LENS_NOT_AVAILABLE`. The client cannot grant
 * itself a lens by asking for one.
 */
enum class LensHint(val wireValue: String) {
    TEACHER("teacher"),
    STUDENT("student"),
    GUARDIAN("guardian"),
    ;

    companion object {
        /** The header the hint travels in. */
        const val HEADER: String = "X-Lens-Hint"

        /**
         * Parse a wire value the **server** sent back.
         *
         * Used to read which lens produced a response, which is the
         * only direction the client may trust.
         *
         * @param value The wire value
         * @return The matching hint, or null when unrecognised
         */
        fun fromWire(value: String): LensHint? =
            entries.firstOrNull { it.wireValue == value }
    }
}
