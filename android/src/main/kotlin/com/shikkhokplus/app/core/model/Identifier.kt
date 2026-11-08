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
 * Whether a field holds something shaped like an email address.
 *
 * **Shape only**: one `@` with something on each side, a dot in the
 * part after it, no spaces, and no longer than the server accepts. It
 * spares a round trip for an obvious slip; the server decides.
 *
 * @param raw The field as typed
 * @return True when it could be an address
 */
fun emailIsWellFormed(raw: String): Boolean {
    val text = raw.trim()
    if (text.isEmpty() || text.length > EMAIL_MAX || text.any { it.isWhitespace() }) return false
    val at = text.indexOf('@')
    if (at <= 0 || at != text.lastIndexOf('@')) return false
    val domain = text.substring(at + 1)
    return domain.contains('.') && !domain.startsWith('.') && !domain.endsWith('.')
}
