package com.shikkhokplus.app.feature.help

import com.shikkhokplus.app.core.network.HelpTicketDetailDto
import com.shikkhokplus.app.core.network.HelpTicketListDto
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * What the help centre needs from the network.
 *
 * Every call is about the signed-in account's own questions: the server
 * reads no lens and no workspace for them, so any role can ask.
 */
interface HelpRepository {
    /**
     * Read the reader's own questions.
     *
     * @return The questions, a refusal, or a transport failure
     */
    suspend fun tickets(): AuthResult<HelpTicketListDto>

    /**
     * Ask a new question.
     *
     * @param subject The one-line summary, trimmed
     * @param body The question, trimmed
     * @return The new question and its thread, a refusal, or a transport failure
     */
    suspend fun ask(subject: String, body: String): AuthResult<HelpTicketDetailDto>

    /**
     * Read one question and its thread. The server marks support's
     * replies seen as it answers.
     *
     * @param ticketId The question
     * @return The thread, a refusal, or a transport failure
     */
    suspend fun ticket(ticketId: String): AuthResult<HelpTicketDetailDto>

    /**
     * Add a message to a question. A closed question reopens.
     *
     * @param ticketId The question
     * @param body The message, trimmed
     * @return The thread as it now stands, a refusal, or a transport failure
     */
    suspend fun reply(ticketId: String, body: String): AuthResult<HelpTicketDetailDto>
}
