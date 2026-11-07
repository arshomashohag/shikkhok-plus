package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire shapes for the signed-in account's own two-step verification
 * settings [0028], under `/v1/me/mfa`.
 *
 * They mirror the server's schemas one-to-one and carry no derived
 * fields: whether it is recommended or required is the server's to say,
 * never the client's to work out from a role [TC-9, D-31].
 */

/**
 * Whether two-step verification is on, and what to suggest.
 *
 * @property enabled An authenticator app is set up
 * @property enabledAt When it was turned on, or null
 * @property recoveryCodesLeft Unused recovery codes
 * @property recommended Suggest it: the account teaches or runs a centre
 * @property required It cannot be turned off: a platform administrator
 */
@Serializable
data class MfaStatusDto(
    @SerialName("enabled") val enabled: Boolean,
    @SerialName("enabled_at") val enabledAt: String? = null,
    @SerialName("recovery_codes_left") val recoveryCodesLeft: Int,
    @SerialName("recommended") val recommended: Boolean,
    @SerialName("required") val required: Boolean,
)

/**
 * A new secret to add to an authenticator app.
 *
 * Shown once, while turning it on, and never stored on the phone.
 *
 * @property secret The base32 secret, for typing in by hand
 * @property otpauthUri The same secret as an `otpauth://` link, which
 *   an authenticator app on this phone opens directly
 */
@Serializable
data class MfaSetupDto(
    @SerialName("secret") val secret: String,
    @SerialName("otpauth_uri") val otpauthUri: String,
)

/**
 * An authenticator code, for confirming setup and for new recovery codes.
 *
 * @property code Six digits from the app
 */
@Serializable
data class MfaCodeRequestDto(
    @SerialName("code") val code: String,
)

/**
 * Proof of the factor, for turning it off: exactly one of the two codes.
 *
 * @property code Six digits from the app, or null
 * @property recoveryCode A recovery code, or null
 */
@Serializable
data class MfaProofRequestDto(
    @SerialName("code") val code: String? = null,
    @SerialName("recovery_code") val recoveryCode: String? = null,
)

/**
 * Ten single-use recovery codes, shown once.
 *
 * @property recoveryCodes The codes, in the server's order
 */
@Serializable
data class MfaRecoveryCodesDto(
    @SerialName("recovery_codes") val recoveryCodes: List<String>,
)
