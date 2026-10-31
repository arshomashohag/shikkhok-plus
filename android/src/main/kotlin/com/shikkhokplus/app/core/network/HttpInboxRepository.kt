package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.inbox.InboxRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post

/**
 * The reader's own inbox, over HTTP.
 *
 * **Every route is `/v1/me/...`**: the server reads and marks only the
 * authenticated account's own messages, and refuses an id that is not.
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
     * Read one message and what it opens to.
     *
     * @param id The message
     * @return The detail, an error envelope, or a transport failure
     */
    override suspend fun detail(id: String): AuthResult<NotificationDetailDto> =
        call { client.get("/v1/me/notifications/$id") }

    /**
     * Mark every message read.
     *
     * @return Done, an error envelope, or a transport failure
     */
    override suspend fun markAllRead(): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/me/notifications/read") }

    /**
     * Mark one message read.
     *
     * @param id The message
     * @return Done, an error envelope, or a transport failure
     */
    override suspend fun markRead(id: String): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/me/notifications/$id/read") }
}
