package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.help.HelpRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * The reader's own help-centre questions, over HTTP.
 *
 * **Every route is `/v1/me/...`**: the server reads and writes only the
 * authenticated account's own questions and answers another's id as not
 * found. Nothing is queued: asking and replying need a connection, and
 * a failure goes back to the screen to retry [TC-8, D-9].
 *
 * @property client The authenticated HTTP client
 */
class HttpHelpRepository(
    private val client: HttpClient,
) : HelpRepository {

    override suspend fun tickets(): AuthResult<HelpTicketListDto> = call { client.get("/v1/me/help/tickets") }

    override suspend fun ask(subject: String, body: String): AuthResult<HelpTicketDetailDto> =
        call { client.post("/v1/me/help/tickets") { setBody(HelpTicketRequestDto(subject, body)) } }

    override suspend fun ticket(ticketId: String): AuthResult<HelpTicketDetailDto> =
        call { client.get("/v1/me/help/tickets/$ticketId") }

    override suspend fun reply(ticketId: String, body: String): AuthResult<HelpTicketDetailDto> =
        call { client.post("/v1/me/help/tickets/$ticketId/messages") { setBody(HelpReplyRequestDto(body)) } }
}
