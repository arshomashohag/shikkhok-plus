package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.invitations.InvitationsRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.post

/**
 * The invitations repository, over HTTP.
 *
 * **This is the acceptance model's client half** [D1]. Before it, a
 * teacher typing a phone number granted a stranger a guardian lens
 * over a child's records; a seat now grants nothing until the person
 * holding it accepts. These four routes are how they do that, and
 * until now nothing could call them.
 *
 * **The list carries no account identifier.** `/v1/invitations`
 * resolves the seats from the authenticated account, so a caller
 * cannot ask about anybody else's.
 *
 * @property client The authenticated HTTP client
 */
class HttpInvitationsRepository(
    private val client: HttpClient,
) : InvitationsRepository {

    /**
     * List the seats awaiting this person's decision.
     *
     * @return The seats, an error envelope, or a transport failure
     */
    override suspend fun list(): AuthResult<List<InvitationDto>> =
        call { client.get("/v1/invitations") }

    /**
     * Read one seat, at the width the server permits [BR1.4].
     *
     * @param enrollmentId The seat to read
     * @return The seat, an error envelope, or a transport failure
     */
    override suspend fun detail(
        enrollmentId: String,
    ): AuthResult<InvitationDto> = call { client.get("/v1/invitations/$enrollmentId") }

    /**
     * Accept a seat, which grants the lens it carries.
     *
     * @param enrollmentId The seat being accepted
     * @return The decided seat, or why the server refused
     */
    override suspend fun accept(
        enrollmentId: String,
    ): AuthResult<DecisionDto> =
        call { client.post("/v1/invitations/$enrollmentId/accept") }

    /**
     * Decline a seat.
     *
     * **What a decline means differs by role, and the server decides
     * it** [BR5.2]: a student's decline stops their fee, a guardian's
     * leaves the student's obligation standing. Nothing here infers
     * which — the screen renders what the server returns.
     *
     * @param enrollmentId The seat being declined
     * @return The decided seat, or why the server refused
     */
    override suspend fun decline(
        enrollmentId: String,
    ): AuthResult<DecisionDto> =
        call { client.post("/v1/invitations/$enrollmentId/decline") }
}
