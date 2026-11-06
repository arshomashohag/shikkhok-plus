package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One person who works at a centre, as its managers keep them.
 *
 * A record grants nothing: app access is a separate membership, reported
 * here as [access].
 *
 * @property staffId The record
 * @property kind `teacher` or `other`
 * @property displayName Their name
 * @property phone Their number, or null for staff kept without one
 * @property email Their email, or null
 * @property roleLabel What they do, for other staff; null for a teacher
 * @property staffHouse House or flat, or null
 * @property staffRoad Road or area, or null
 * @property staffCity City or district, or null
 * @property staffPostcode Four digits, or null
 * @property payBasis `monthly`, `per_class` or `none`
 * @property payRate The rate, with a paid basis; null with `none`
 * @property joinedOn When they joined, `yyyy-MM-dd`
 * @property leftOn Their last day, or null while they work here
 * @property status `active` or `left`
 * @property access `none`, `invited`, `declined`, `active` or `revoked`
 */
@Serializable
data class StaffDto(
    @SerialName("staff_id") val staffId: String,
    @SerialName("kind") val kind: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("phone") val phone: String? = null,
    @SerialName("email") val email: String? = null,
    @SerialName("role_label") val roleLabel: String? = null,
    @SerialName("staff_house") val staffHouse: String? = null,
    @SerialName("staff_road") val staffRoad: String? = null,
    @SerialName("staff_city") val staffCity: String? = null,
    @SerialName("staff_postcode") val staffPostcode: String? = null,
    @SerialName("pay_basis") val payBasis: String,
    @SerialName("pay_rate") val payRate: Money? = null,
    @SerialName("joined_on") val joinedOn: String,
    @SerialName("left_on") val leftOn: String? = null,
    @SerialName("status") val status: String,
    @SerialName("access") val access: String,
) {
    /** Whether they are a teacher, invited to the app, rather than other staff. */
    val isTeacher: Boolean get() = kind == "teacher"

    /** Whether they have left. */
    val hasLeft: Boolean get() = status == "left"
}

/**
 * A staff record's details, the shape every write shares.
 *
 * Every field is sent, null included: an edit replaces the record's
 * details, so an omitted field would be ambiguous with "leave alone".
 *
 * @property displayName Their name
 * @property phone Their number; required for a teacher, who is invited by it
 * @property email Their email, or null
 * @property roleLabel What they do, for other staff, or null
 * @property staffHouse House or flat, or null
 * @property staffRoad Road or area, or null
 * @property staffCity City or district, or null
 * @property staffPostcode Four Latin digits, or null
 * @property payBasis `monthly`, `per_class` or `none`
 * @property payRate The rate, with a paid basis; null with `none`
 * @property joinedOn When they joined, or null for today
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class StaffBodyDto(
    @EncodeDefault @SerialName("display_name") val displayName: String,
    @SerialName("phone") val phone: String? = null,
    @EncodeDefault @SerialName("email") val email: String? = null,
    @SerialName("role_label") val roleLabel: String? = null,
    @EncodeDefault @SerialName("staff_house") val staffHouse: String? = null,
    @EncodeDefault @SerialName("staff_road") val staffRoad: String? = null,
    @EncodeDefault @SerialName("staff_city") val staffCity: String? = null,
    @EncodeDefault @SerialName("staff_postcode") val staffPostcode: String? = null,
    @EncodeDefault @SerialName("pay_basis") val payBasis: String,
    @EncodeDefault @SerialName("pay_rate") val payRate: Money? = null,
    @SerialName("joined_on") val joinedOn: String? = null,
)

/**
 * The body of `POST /v1/centre/staff/{id}/leave`.
 *
 * @property leftOn Their last day, or null for today
 */
@Serializable
data class StaffLeaveDto(
    @SerialName("left_on") val leftOn: String? = null,
)
