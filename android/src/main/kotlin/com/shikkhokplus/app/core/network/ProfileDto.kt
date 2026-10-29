package com.shikkhokplus.app.core.network

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
 * @property address Their address, or null
 * @property phone The number this account signs in with, shown
 *   read-only and typed back to confirm deletion
 */
@Serializable
data class MeDto(
    val lenses: List<LensEntryDto> = emptyList(),
    @SerialName("self_name") val selfName: String? = null,
    val address: String? = null,
    val phone: String? = null,
)

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
 * @property address The new address, or null to leave it alone
 */
@Serializable
data class ProfileUpdateDto(
    @SerialName("self_name") val selfName: String? = null,
    val address: String? = null,
)
