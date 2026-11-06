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
 * @property phone The number they were invited on
 * @property role `manager` or `teacher`
 * @property decision `pending`, `accepted` or `declined`
 * @property revoked Whether a manager removed them
 * @property isYou Whether this is the signed-in account's own membership
 */
@Serializable
data class MemberDto(
    @SerialName("member_id") val memberId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("phone") val phone: String,
    @SerialName("role") val role: String,
    @SerialName("decision") val decision: String,
    @SerialName("revoked") val revoked: Boolean = false,
    @SerialName("is_you") val isYou: Boolean = false,
)

/**
 * The body of `POST /v1/centre/members`.
 *
 * @property displayName Their name
 * @property phone Their number, in any common spelling
 * @property role `manager` or `teacher`
 */
@Serializable
data class MemberInviteDto(
    @SerialName("display_name") val displayName: String,
    @SerialName("phone") val phone: String,
    @SerialName("role") val role: String,
)

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
