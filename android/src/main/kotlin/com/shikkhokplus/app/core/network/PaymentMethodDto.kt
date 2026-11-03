package com.shikkhokplus.app.core.network

import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One payment method as the server returns it.
 *
 * @property methodId The method
 * @property kind `mobile` or `bank`
 * @property provider The mobile service, or the bank's name
 * @property mobileNumber The number, mobile methods only
 * @property accountNumber The account number, bank methods only
 * @property accountName The account holder, bank methods only
 * @property branchName The branch, bank methods only
 * @property note Optional text shown with the method
 */
@Serializable
data class PaymentMethodDto(
    @SerialName("method_id") val methodId: String,
    @SerialName("kind") val kind: String,
    @SerialName("provider") val provider: String? = null,
    @SerialName("mobile_number") val mobileNumber: String? = null,
    @SerialName("account_number") val accountNumber: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("branch_name") val branchName: String? = null,
    @SerialName("note") val note: String? = null,
)

/**
 * The body of a create or a full replace.
 *
 * Every field is sent, null included: a PATCH replaces the method in
 * full, so an omitted field would be ambiguous with "leave alone".
 *
 * @property kind `mobile` or `bank`
 * @property provider The mobile service, or the bank's name
 * @property mobileNumber The number, mobile methods only
 * @property accountNumber The account number, bank methods only
 * @property accountName The account holder, bank methods only
 * @property branchName The branch, bank methods only
 * @property note Optional text shown with the method
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class PaymentMethodRequestDto(
    @EncodeDefault @SerialName("kind") val kind: String,
    @EncodeDefault @SerialName("provider") val provider: String? = null,
    @EncodeDefault @SerialName("mobile_number") val mobileNumber: String? = null,
    @EncodeDefault @SerialName("account_number") val accountNumber: String? = null,
    @EncodeDefault @SerialName("account_name") val accountName: String? = null,
    @EncodeDefault @SerialName("branch_name") val branchName: String? = null,
    @EncodeDefault @SerialName("note") val note: String? = null,
)
