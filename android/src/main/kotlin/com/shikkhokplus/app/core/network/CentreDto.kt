package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The body of `POST /v1/centres`: open a coaching centre.
 *
 * @property name The centre's name
 * @property managerName The opener's name as the centre shows it
 */
@Serializable
data class CentreCreateDto(
    @SerialName("name") val name: String,
    @SerialName("manager_name") val managerName: String,
)

/**
 * A centre just opened; the opener is its first manager.
 *
 * @property ownerId The centre's workspace
 * @property name Its name
 */
@Serializable
data class CentreDto(
    @SerialName("owner_id") val ownerId: String,
    @SerialName("name") val name: String,
)

/**
 * One member of a centre, as its managers see them.
 *
 * @property memberId The membership
 * @property displayName The name the manager typed
 * **[phone] is nullable, and was not** (functional-spec § 1 defect 1,
 * NFR6.2). `MemberResponse.phone` is `string | null` since a member can
 * be invited by email alone (C2); declared non-null, one such invitation
 * failed the decode of the whole list and took the members screen away
 * from every manager of the centre.
 *
 * @property memberId The membership
 * @property displayName The name the manager typed
 * @property phone The number they were invited on, or null for an
 *   invitation by email alone
 * @property role `manager` or `teacher`
 * @property decision `pending`, `accepted` or `declined`
 * @property revoked Whether a manager removed them
 * @property isYou Whether this is the signed-in account's own membership
 * @property invitedEmail The address they were invited on, or null.
 *   Centre-written, never the member's own account address [FR6.4]
 */
@Serializable
data class MemberDto(
    @SerialName("member_id") val memberId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("phone") val phone: String? = null,
    @SerialName("role") val role: String,
    @SerialName("decision") val decision: String,
    @SerialName("revoked") val revoked: Boolean = false,
    @SerialName("is_you") val isYou: Boolean = false,
    @SerialName("invited_email") val invitedEmail: String? = null,
) {
    // The contacts are someone else's, typed by a manager [NFR3.2].
    override fun toString(): String =
        "MemberDto(memberId=$memberId, role=$role, decision=$decision, revoked=$revoked, isYou=$isYou, " +
            "phone=***, invitedEmail=***)"
}

/**
 * The body of `POST /v1/centre/members`: a phone, an email, or both.
 *
 * **At least one of the two** [FR6.4]; the server refuses neither with
 * a 422. A blank one is left out of the body by the client's JSON
 * settings, which omit nulls.
 *
 * @property displayName Their name
 * @property phone Their number, in any common spelling, or null
 * @property role `manager` or `teacher`
 * @property email Their address, or null
 */
@Serializable
data class MemberInviteDto(
    @SerialName("display_name") val displayName: String,
    @SerialName("phone") val phone: String? = null,
    @SerialName("role") val role: String,
    @SerialName("email") val email: String? = null,
) {
    override fun toString(): String = "MemberInviteDto(role=$role, phone=***, email=***)"
}

/**
 * A centre's offer to the signed-in account.
 *
 * @property memberId The membership
 * @property centreName The centre
 * @property role `manager` or `teacher`
 * @property decision `pending` or `declined`
 */
@Serializable
data class MembershipDto(
    @SerialName("member_id") val memberId: String,
    @SerialName("centre_name") val centreName: String,
    @SerialName("role") val role: String,
    @SerialName("decision") val decision: String,
)

/**
 * The answer to accepting or declining an offer.
 *
 * @property memberId The membership
 * @property decision `accepted` or `declined`
 */
@Serializable
data class MembershipDecisionDto(
    @SerialName("member_id") val memberId: String,
    @SerialName("decision") val decision: String,
)
