package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.inbox.InboxRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post

/**
 * The reader's own inbox, over HTTP.
 *
 * **Both routes are `/v1/me/...` and carry no identifier**: the server
 * reads and marks the authenticated account's own messages.
 *
 * @property client The authenticated HTTP client
 */
class HttpInboxRepository(
    private val client: HttpClient,
) : InboxRepository {

    /**
     * Read the inbox.
     *
     * @return The messages, an error envelope, or a transport failure
     */
    override suspend fun inbox(): AuthResult<InboxDto> = call { client.get("/v1/me/notifications") }

    /**
     * Mark every message read.
     *
     * @return Done, an error envelope, or a transport failure
     */
    override suspend fun markRead(): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/me/notifications/read") }
}
