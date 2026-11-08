package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire shapes for the auth endpoints.
 *
 * These mirror the server's schemas one-to-one and carry **no derived
 * fields**. A derived value here would be a business rule living on the
 * client, which [TC-9, D-31] forbid outright.
 */

/**
 * Ask the server to send a code: to a number, or to an email address.
 *
 * **Exactly one of the two** is set; the other is left out of the body
 * rather than sent as null, because the client's JSON omits nulls. The
 * server refuses both or neither.
 *
 * @property phone Typed by the user. Never read from the SIM [AC1.1.6]
 * @property email Typed by the user
 */
@Serializable
data class IssueRequest(
    @SerialName("phone") val phone: String? = null,
    @SerialName("email") val email: String? = null,
)

/**
 * The server's reply to an issue request.
 *
 * One field, and it is the same for every number. The client must not
 * branch on anything here: a known and an unknown number are
 * indistinguishable by design [BR2.7], and a client that inferred
 * otherwise would rebuild the oracle the server closed.
 */
@Serializable
data class IssueResponse(
    @SerialName("status") val status: String,
)

/**
 * Present a code for verification, for the phone or the email it was
 * sent to. Used by sign-in's code flow and by adding a contact.
 *
 * @property phone The number the code went to, or null
 * @property email The address the code went to, or null
 * @property code The six digits
 */
@Serializable
data class VerifyRequest(
    @SerialName("phone") val phone: String? = null,
    @SerialName("email") val email: String? = null,
    @SerialName("code") val code: String,
)

/**
 * Sign in with an identifier and a password.
 *
 * **The password is in this body and nowhere else**: it is never
 * logged, never stored, and the request object is dropped once sent.
 *
 * @property phone The number, or null
 * @property email The address, or null
 * @property password What the person typed
 */
@Serializable
data class PasswordSignInRequest(
    @SerialName("phone") val phone: String? = null,
    @SerialName("email") val email: String? = null,
    @SerialName("password") val password: String,
) {
    override fun toString(): String = "PasswordSignInRequest(phone=$phone, email=$email, password=***)"
}

/**
 * Finish the code flow by choosing a password.
 *
 * @property token What `POST /v1/auth/verify` returned as
 *   `password_setup_token`
 * @property password The chosen password
 * @property code The authenticator code, when verify said
 *   `mfa_required`; null otherwise
 * @property recoveryCode A recovery code instead of [code], or null
 */
@Serializable
data class PasswordSetupRequest(
    @SerialName("token") val token: String,
    @SerialName("password") val password: String,
    @SerialName("code") val code: String? = null,
    @SerialName("recovery_code") val recoveryCode: String? = null,
) {
    override fun toString(): String = "PasswordSetupRequest(token=***, password=***)"
}

/**
 * Set a first password, or change one, while signed in.
 *
 * @property currentPassword Required when the account already has one;
 *   left out of the body when it has none
 * @property newPassword The password to set
 */
@Serializable
data class MePasswordRequest(
    @SerialName("current_password") val currentPassword: String? = null,
    @SerialName("new_password") val newPassword: String,
) {
    override fun toString(): String = "MePasswordRequest(current_password=***, new_password=***)"
}

/** Present a refresh token for rotation. */
@Serializable
data class RefreshRequest(
    @SerialName("refresh_token") val refreshToken: String,
)

/**
 * A freshly issued token pair.
 *
 * **No role and no lens field**, matching the server. The client learns
 * what it may do from each response, never from the token.
 */
@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("expires_in") val expiresIn: Int,
)

/**
 * What a verified code or a password sign-in yields.
 *
 * **Two routes answer with this shape, differently.**
 * `POST /v1/auth/password` (sign-in) carries the token pair, or the
 * authenticator step [0028]. `POST /v1/auth/verify` (a one-time code)
 * never carries tokens any more: it carries [passwordSetupToken], which
 * `POST /v1/auth/password/setup` exchanges, with a chosen password, for
 * the pair. The setup token is kept in memory only, like the challenge.
 *
 * **Parsed tolerantly, both shapes.** For an account without two-step
 * verification the server sends exactly the pair it always sent, now
 * with `mfa_required: false`; a server from before the authenticator
 * step sends the pair alone, which reads the same way because
 * [mfaRequired] defaults to false. For an account with it on, the token
 * fields are absent and [mfaChallenge] carries the sign-in to
 * `POST /v1/auth/mfa`. The challenge grants nothing by itself and is
 * kept in memory only, never stored.
 *
 * @property accessToken The bearer token, when no second step is needed
 * @property refreshToken The rotation token, likewise
 * @property expiresIn Access-token lifetime in seconds, likewise
 * @property mfaRequired True when an authenticator code must follow
 * @property mfaChallenge Carries the sign-in to the second step
 * @property mfaExpiresIn Seconds until the challenge lapses; shown
 *   nowhere, because the server says when it has lapsed
 * @property passwordSetupToken From a verified code: carries the code
 *   flow to choosing a password; null from a password sign-in
 * @property passwordSetupExpiresIn Seconds until that token lapses; shown
 *   nowhere, because the server says when it has lapsed
 */
@Serializable
data class VerifyResponse(
    @SerialName("access_token") val accessToken: String? = null,
    @SerialName("refresh_token") val refreshToken: String? = null,
    @SerialName("expires_in") val expiresIn: Int? = null,
    @SerialName("mfa_required") val mfaRequired: Boolean = false,
    @SerialName("mfa_challenge") val mfaChallenge: String? = null,
    @SerialName("mfa_expires_in") val mfaExpiresIn: Int? = null,
    @SerialName("password_setup_token") val passwordSetupToken: String? = null,
    @SerialName("password_setup_expires_in") val passwordSetupExpiresIn: Int? = null,
)

/**
 * The second step of signing in: the challenge and exactly one code.
 *
 * The absent code is left out of the body rather than sent as null,
 * because the client's JSON omits nulls.
 *
 * @property challenge From [VerifyResponse.mfaChallenge]
 * @property code Six digits from the authenticator app, or null
 * @property recoveryCode A recovery code, or null
 */
@Serializable
data class MfaSignInRequest(
    @SerialName("challenge") val challenge: String,
    @SerialName("code") val code: String? = null,
    @SerialName("recovery_code") val recoveryCode: String? = null,
)

/**
 * The one error envelope every failure carries.
 *
 * `retryable` is **read, never inferred**. The client is forbidden
 * business logic, so it does not decide retryability from an HTTP
 * status — it is told [TC-9].
 *
 * `messageKey` names a string resource rather than carrying English
 * text, which is what makes a Bangla-first UI possible at all: a
 * server-sent message cannot be localized by the client.
 */
@Serializable
data class ErrorBody(
    @SerialName("code") val code: String,
    @SerialName("retryable") val retryable: Boolean,
    @SerialName("message_key") val messageKey: String,
    // Typed per code and rendered, never interpreted: for a wrong sign-in
    // code it carries `attempts_left`, which the code screen shows.
    @SerialName("details") val details: Map<String, String>? = null,
)

/** The envelope wrapping [ErrorBody]. */
@Serializable
data class ErrorEnvelope(
    @SerialName("error") val error: ErrorBody,
)
