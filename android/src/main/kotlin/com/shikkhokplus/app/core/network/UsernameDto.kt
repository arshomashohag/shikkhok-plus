package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire shapes for usernames and for replacing or removing a contact
 * [U3; C1 as amended, C2].
 *
 * **Every value travels in a body, never in a URL** [NFR3.1, NFR3.5]: a
 * username is owner-private and low-entropy, and a URL ends up in proxy
 * and server access logs. **Every class that holds a username, a
 * contact or a password masks it in `toString`** [NFR3.2], so a stray
 * log line or a test failure message cannot print one.
 */

/**
 * Ask whether a name could be taken: the public lookup at sign-up and
 * the authenticated one on the gate and the rename form.
 *
 * @property username The candidate, trimmed
 */
@Serializable
data class UsernameAvailabilityRequest(
    @SerialName("username") val username: String,
) {
    override fun toString(): String = "UsernameAvailabilityRequest(username=***)"
}

/**
 * What a lookup said about a name.
 *
 * **[status] stays a string** [NFR6.3]: a value this client does not
 * know decodes and is mapped to "could not check" rather than failing
 * the read. `unavailable` is the one answer for taken and held alike
 * (ADR-007); nothing here could tell them apart.
 *
 * @property status `available`, `unavailable`, `invalid` or `reserved`
 * @property messageKey For `invalid`, which rule failed; otherwise null
 */
@Serializable
data class UsernameAvailabilityDto(
    @SerialName("status") val status: String,
    @SerialName("message_key") val messageKey: String? = null,
)

/**
 * Choose the first username, or rename.
 *
 * @property username The candidate, trimmed
 * @property password The account's password for a rename; null, and so
 *   left out of the body, for the first choice [FR5.4]
 */
@Serializable
data class UsernameChangeRequest(
    @SerialName("username") val username: String,
    @SerialName("password") val password: String? = null,
) {
    override fun toString(): String = "UsernameChangeRequest(username=***, password=***)"
}

/**
 * The username as stored, and when it may next change.
 *
 * @property username The display form, as stored. Owner-only [FR9]
 * @property nextChangeAt When an ordinary rename is next allowed, as the
 *   server's ISO 8601 instant, or null when no limit applies now. Shown,
 *   never computed from [FR11.3]
 */
@Serializable
data class UsernameChangeDto(
    @SerialName("username") val username: String,
    @SerialName("next_change_at") val nextChangeAt: String? = null,
) {
    override fun toString(): String = "UsernameChangeDto(username=***, nextChangeAt=$nextChangeAt)"
}

/**
 * Ask for a code to REPLACE the account's phone or email [FR8.2].
 *
 * The same route as adding one (`POST /v1/me/contact`), with the
 * password: the server reads a request for a kind the account already
 * holds as a replacement, and asks for the password then (C2).
 *
 * @property phone The new number, or null
 * @property email The new address, or null
 * @property password The account's password
 */
@Serializable
data class ContactChangeRequest(
    @SerialName("phone") val phone: String? = null,
    @SerialName("email") val email: String? = null,
    @SerialName("password") val password: String? = null,
) {
    override fun toString(): String = "ContactChangeRequest(phone=***, email=***, password=***)"
}

/**
 * Remove the account's phone or email [FR8.4].
 *
 * @property kind `phone` or `email`
 * @property password The account's password
 */
@Serializable
data class ContactRemoveRequest(
    @SerialName("kind") val kind: String,
    @SerialName("password") val password: String,
) {
    override fun toString(): String = "ContactRemoveRequest(kind=$kind, password=***)"
}
