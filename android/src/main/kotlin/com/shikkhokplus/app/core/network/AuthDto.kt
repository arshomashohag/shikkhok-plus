package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire shapes for the three auth endpoints.
 *
 * These mirror the server's schemas one-to-one and carry **no derived
 * fields**. A derived value here would be a business rule living on the
 * client, which [TC-9, D-31] forbid outright.
 */

/** Ask the server to send a code to a number the user typed. */
@Serializable
data class IssueRequest(
    /** Typed by the user. Never read from the SIM [AC1.1.6]. */
    @SerialName("phone") val phone: String,
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

/** Present a code for verification. */
@Serializable
data class VerifyRequest(
    @SerialName("phone") val phone: String,
    @SerialName("code") val code: String,
)

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
 * What a verified SMS code yields: the token pair, or the authenticator
 * step [0028].
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
 */
@Serializable
data class VerifyResponse(
    @SerialName("access_token") val accessToken: String? = null,
    @SerialName("refresh_token") val refreshToken: String? = null,
    @SerialName("expires_in") val expiresIn: Int? = null,
    @SerialName("mfa_required") val mfaRequired: Boolean = false,
    @SerialName("mfa_challenge") val mfaChallenge: String? = null,
    @SerialName("mfa_expires_in") val mfaExpiresIn: Int? = null,
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
