package com.shikkhokplus.app.core.network

import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.http.ContentType
import io.ktor.http.URLProtocol
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

/**
 * Builds the one HTTP client the app uses.
 *
 * **The base URL is required, not defaulted.** A default would be
 * either a developer's machine — shipped to a phone — or a production
 * host reached from a debug build. Both are worse than a compile-time
 * requirement to say which.
 *
 * **`https` is enforced here and not merely assumed.** The Android
 * manifest sets no `usesCleartextTraffic`, so a plaintext request fails
 * at the platform — but it fails with a network error that looks like
 * any other, and a developer debugging it reaches for the manifest flag.
 * Refusing the URL at construction names the actual problem.
 */
object ApiClient {

    /**
     * The JSON configuration, and every option here is a decision.
     *
     * `ignoreUnknownKeys` is **true** because an installed app cannot be
     * forced to update [D-26]: the server adds fields additively, and a
     * client that refused an unknown one would break on every server
     * deploy until the user updated.
     *
     * `explicitNulls` is **false** so an absent optional is omitted
     * rather than sent as `null` — the backend distinguishes "not
     * supplied" from "explicitly null" on PATCH bodies.
     *
     * `isLenient` is **false**, deliberately. A lenient parser accepts
     * an unquoted number where a money string belongs, which is the
     * exact failure the Money serializer exists to make loud.
     */
    val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        isLenient = false
    }

    /**
     * Build a client for one backend.
     *
     * @param baseUrl The backend's origin, `https` in every real build
     * @param engine The engine, overridden by tests with a mock
     * @param tokenStore Supplies the access token for each request
     * @param onSessionEnded Called when an expired session cannot be
     *   renewed because the server refused the stored refresh token
     * @return The configured client
     * @throws IllegalArgumentException If [baseUrl] is not https
     */
    fun build(
        baseUrl: String,
        engine: HttpClientEngine = OkHttp.create(),
        tokenStore: TokenStore = TokenStore.InMemory(),
        onSessionEnded: () -> Unit = {},
    ): HttpClient {
        val url = io.ktor.http.Url(baseUrl)
        require(url.protocol == URLProtocol.HTTPS || isLoopback(url.host)) {
            "The backend must be reached over https, got '$baseUrl'. " +
                "Plaintext is permitted only for a loopback host during " +
                "local development."
        }

        val client = HttpClient(engine) {
            // A failed request returns a response rather than throwing,
            // so the repository maps it through the taxonomy instead of
            // catching an exception for an ordinary 404.
            expectSuccess = false

            install(ContentNegotiation) { json(json) }

            defaultRequest {
                url(baseUrl)
                contentType(ContentType.Application.Json)
                tokenStore.accessToken()?.let { token ->
                    headers.append("Authorization", "Bearer $token")
                }
            }
        }

        // An expired request is renewed and repeated, mid-session, the
        // way a cold start renews: see `SessionRenewal`.
        SessionRenewal(baseUrl, tokenStore, onSessionEnded).install(client)
        return client
    }

    /**
     * Report whether a host is the loopback interface.
     *
     * `10.0.2.2` is the emulator's route to the host machine and is
     * loopback from the developer's point of view, which is the only
     * point of view this exemption serves.
     *
     * @param host The host to test
     * @return True when plaintext is permissible for it
     */
    private fun isLoopback(host: String): Boolean =
        host == "localhost" || host == "127.0.0.1" || host == "10.0.2.2"
}
