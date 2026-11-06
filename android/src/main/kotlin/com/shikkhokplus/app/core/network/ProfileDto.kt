package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.PostalAddress
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One lens this account can take, with how many seats it covers.
 *
 * @property kind `teacher`, `student` or `guardian`
 * @property count How many batches or enrollments it reaches
 */
@Serializable
data class LensEntryDto(
    val kind: String,
    val count: Int = 0,
)

/**
 * What `GET /v1/me` reports: the lenses, and this person's own row.
 *
 * **No role field, deliberately.** The list says what is available and
 * which one the person wants is their choice; a server-chosen default
 * would be a stored role by another name [TC-11, D-2].
 *
 * `address` is owner-private [BR3.4] and sits in the set that reaches
 * no teacher-lens response. It is here because this is the owner
 * reading their own row.
 *
 * @property lenses Every available lens, teacher first
 * @property selfName The name this person chose, or null
 * @property address Their free-text address from before 2026-11-05, or null
 * @property addressHouse House or flat, or null
 * @property addressRoad Road or area, or null
 * @property addressCity City or district, or null
 * @property addressPostcode Four digits, or null
 * @property phone The number this account signs in with, shown
 *   read-only and typed back to confirm deletion
 * @property workspaces The workspaces this account manages, solo first;
 *   the server's own answer to which a teacher may act on
 */
@Serializable
data class MeDto(
    val lenses: List<LensEntryDto> = emptyList(),
    @SerialName("self_name") val selfName: String? = null,
    val address: String? = null,
    @SerialName("address_house") val addressHouse: String? = null,
    @SerialName("address_road") val addressRoad: String? = null,
    @SerialName("address_city") val addressCity: String? = null,
    @SerialName("address_postcode") val addressPostcode: String? = null,
    val phone: String? = null,
    val workspaces: List<WorkspaceDto> = emptyList(),
) {
    /** The address in its four parts, empty where none is stored. */
    val postal: PostalAddress
        get() =
            PostalAddress(
                house = addressHouse.orEmpty(),
                road = addressRoad.orEmpty(),
                city = addressCity.orEmpty(),
                postcode = addressPostcode.orEmpty(),
            )

    /** The address to read back: the four parts, or the older free text. */
    val shownAddress: String?
        get() = postal.oneLine() ?: address
}

/**
 * What a person may change about themselves.
 *
 * **Name and address only.** The phone number is the login and
 * changes through the OTP path; a role is computed per request and
 * has no stored field to set.
 *
 * Both are optional and omitting one leaves it unchanged, so a single
 * edited field can be saved without resending the other.
 *
 * @property selfName The new name, or null to leave it alone
 * @property addressHouse The new house or flat, or null to leave it alone
 * @property addressRoad The new road or area, or null to leave it alone
 * @property addressCity The new city or district, or null to leave it alone
 * @property addressPostcode The new postcode, or null to leave it alone
 */
@Serializable
data class ProfileUpdateDto(
    @SerialName("self_name") val selfName: String? = null,
    @SerialName("address_house") val addressHouse: String? = null,
    @SerialName("address_road") val addressRoad: String? = null,
    @SerialName("address_city") val addressCity: String? = null,
    @SerialName("address_postcode") val addressPostcode: String? = null,
)

/**
 * One workspace a teacher may act on.
 *
 * @property ownerId The workspace, sent back as `X-Workspace-Id`
 * @property kind `solo` or `centre`
 * @property name The centre's name; null for the solo workspace
 */
@Serializable
data class WorkspaceDto(
    @SerialName("owner_id") val ownerId: String,
    @SerialName("kind") val kind: String,
    @SerialName("name") val name: String? = null,
) {
    /** Whether this is a coaching centre rather than the solo workspace. */
    val isCentre: Boolean get() = kind == "centre"
}
