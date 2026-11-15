package com.shikkhokplus.app.core.model

/**
 * Which kind of identifier a person signs up or signs in with.
 *
 * Exactly one is sent on every request that names an account: the
 * server refuses a body carrying both or neither.
 */
enum class IdentifierKind {
    /** A mobile number, typed by the person and never read from the SIM [TC-4, D-35]. */
    PHONE,

    /** An email address. */
    EMAIL,
}

/**
 * A phone number or an email address, as the person typed it.
 *
 * **Format only, never policy.** [isWellFormed] spares a round trip for
 * a value that cannot be either; whether an account exists for it, and
 * every other rule, is the server's to decide [TC-9, D-31].
 *
 * @property kind Which of the two it is
 * @property value What was typed; an email is trimmed when sent, and the
 *   server lowercases it
 */
data class Identifier(
    val kind: IdentifierKind,
    val value: String,
) {
    /** The number, when this is one; null otherwise. */
    val phone: String? get() = value.takeIf { kind == IdentifierKind.PHONE }

    /** The address, trimmed, when this is one; null otherwise. */
    val email: String? get() = value.trim().takeIf { kind == IdentifierKind.EMAIL }

    // The person's own number or address is never printed [NFR3.2].
    override fun toString(): String = "Identifier(kind=$kind, value=***)"

    companion object {
        /**
         * A phone identifier.
         *
         * @param number The number as typed
         * @return The identifier
         */
        fun phone(number: String): Identifier = Identifier(IdentifierKind.PHONE, number)

        /**
         * An email identifier.
         *
         * @param address The address as typed
         * @return The identifier
         */
        fun email(address: String): Identifier = Identifier(IdentifierKind.EMAIL, address)
    }
}

/** The longest email address the server accepts. */
const val EMAIL_MAX: Int = 254

/**
 * The server's own email shape (`app/accounts/identifier.py`), matched
 * against the whole trimmed value: one `@`, no whitespace, a dot in the
 * domain with something after it.
 */
private val EMAIL_SHAPE = Regex("""[^@\s]+@[^@\s]+\.[^@\s]+""")

/**
 * Whether a field holds something shaped like an email address.
 *
 * **Shape only, and never stricter than the server** [FR11.3, NFR3.10].
 * The pattern and the 254-character cap are the server's own, so a value
 * the server accepts is never refused here: an earlier, hand-written
 * check refused `a@b.c.` and `a@.b.c`, both of which the server takes.
 * It spares a round trip for an obvious slip; the server decides.
 *
 * @param raw The field as typed
 * @return True when it could be an address
 */
fun emailIsWellFormed(raw: String): Boolean {
    val text = raw.trim()
    return text.length <= EMAIL_MAX && EMAIL_SHAPE.matches(text)
}
