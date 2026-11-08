package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.PostalAddress
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.auth.SignupRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * The signup repository, over HTTP.
 *
 * **The gap this closes.** D1 shipped `SignupScreen`, `SignupUiState`
 * and `SignupStateMapper` — the whole client-side state machine, with
 * tests — and nothing that could reach the server. The two endpoints
 * have existed in the committed contract since D1; no caller did.
 * Without this, the first screen asks for a number, says a code will
 * arrive "if the number is registered", and offers no way to register.
 *
 * **Three outcomes, not two**, matching [HttpAuthRepository]: a
 * transport failure and a server refusal are different events and the
 * screen renders them differently. Collapsing them would put a retry
 * policy in the client, which is business logic [TC-9, D-31].
 *
 * @property client The configured HTTP client
 */
class HttpSignupRepository(
    private val client: HttpClient,
) : SignupRepository {

    /**
     * Ask whether a teacher already recorded this number.
     *
     * **Unauthenticated by necessity**: the person asking has no
     * account yet. The response is deliberately narrow — a flag, a
     * correctable name, a role — and names neither teacher nor batch,
     * because anything more makes this an oracle for who teaches whom,
     * readable by anyone who can type a phone number [BR2.3, AC1.12.2].
     *
     * @param phone The number the person typed, never read from the SIM
     * @return What the server will say about it
     */
    override suspend fun lookup(phone: String): AuthResult<AlreadyAddedDto> =
        call {
            client.get("/v1/accounts/already-added") {
                parameter("phone", phone)
            }
        }

    /**
     * Create an account for a phone or an email nobody has registered.
     *
     * **This does not sign the person in.** The response carries no
     * token: the account exists and an OTP is on its way, and the
     * person verifies through the existing flow, which is where the
     * seven abuse controls live [BR2.2]. A signup that authenticated
     * directly would be a second, weaker way in.
     *
     * @param identifier The phone or email this identity is keyed on
     * @param role The claimed role; nothing verifies it [BR4.2]
     * @param selfName The name the person chose for themselves
     * @param address Owner-private, in its four parts
     * @param centreName The coaching centre to open, or null
     * @return The new account and where the code went
     */
    override suspend fun signup(
        identifier: Identifier,
        role: String,
        selfName: String,
        address: PostalAddress,
        centreName: String?,
    ): AuthResult<SignupResponseDto> =
        call {
            client.post("/v1/accounts") {
                setBody(
                    SignupRequestDto(
                        phone = identifier.phone,
                        email = identifier.email,
                        role = role,
                        selfName = selfName,
                        addressHouse = address.house.trim(),
                        addressRoad = address.road.trim(),
                        addressCity = address.city.trim(),
                        addressPostcode = address.latinPostcode,
                        centreName = centreName,
                    ),
                )
            }
        }
}
