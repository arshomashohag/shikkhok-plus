package com.shikkhokplus.app.feature.help

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.HelpMessageDto
import com.shikkhokplus.app.core.network.HelpTicketDetailDto
import com.shikkhokplus.app.core.network.HelpTicketDto
import com.shikkhokplus.app.core.network.HelpTicketListDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The help centre's three state machines -- the list, the Ask form and a
 * thread -- and the mapping beneath them, as plain JVM tests.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HelpViewModelsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun ticket(id: String = "t-1", status: String = "open", newReply: Boolean = false) =
        HelpTicketDto(
            ticketId = id,
            subject = "Cannot add a student",
            status = status,
            createdAt = "2026-11-06T04:00:00Z",
            updatedAt = "2026-11-06T05:30:00Z",
            hasNewReply = newReply,
            preview = "The add button does nothing.",
        )

    private fun detail(status: String = "open", vararg authors: String = arrayOf("requester")) =
        HelpTicketDetailDto(
            ticket = ticket(status = status),
            messages =
                authors.mapIndexed { i, author ->
                    HelpMessageDto("m-$i", author, "message $i", "2026-11-06T0$i:00:00Z")
                },
        )

    private fun refused(key: String, retryable: Boolean) =
        AuthResult.Refused(ErrorEnvelope(ErrorBody(code = "X", retryable = retryable, messageKey = key)))

    /** A help centre whose answers each test sets, recording what was sent. */
    private class FakeHelp : HelpRepository {
        var list: AuthResult<HelpTicketListDto> = AuthResult.TransportFailure
        var asked: AuthResult<HelpTicketDetailDto> = AuthResult.TransportFailure
        var read: AuthResult<HelpTicketDetailDto> = AuthResult.TransportFailure
        var replied: AuthResult<HelpTicketDetailDto> = AuthResult.TransportFailure
        var gate: CompletableDeferred<Unit>? = null
        val asks = mutableListOf<Pair<String, String>>()
        val replies = mutableListOf<Pair<String, String>>()
        val reads = mutableListOf<String>()
        var listReads = 0

        override suspend fun tickets(): AuthResult<HelpTicketListDto> {
            listReads++
            gate?.await()
            return list
        }

        override suspend fun ask(subject: String, body: String): AuthResult<HelpTicketDetailDto> {
            asks += subject to body
            gate?.await()
            return asked
        }

        override suspend fun ticket(ticketId: String): AuthResult<HelpTicketDetailDto> {
            reads += ticketId
            return read
        }

        override suspend fun reply(ticketId: String, body: String): AuthResult<HelpTicketDetailDto> {
            replies += ticketId to body
            gate?.await()
            return replied
        }
    }

    // ----- My questions --------------------------------------------------

    @Test
    fun `the list starts loading and maps the server's order, statuses and count`() = runTest(dispatcher) {
        val repo = FakeHelp()
        repo.list =
            AuthResult.Ok(
                HelpTicketListDto(
                    listOf(ticket("t-3", "answered", newReply = true), ticket("t-2", "open"), ticket("t-1", "closed")),
                    newReplies = 1,
                ),
            )
        val model = HelpListViewModel(repo)
        assertEquals(HelpListUiState.Loading, model.state.value)

        model.load()
        advanceUntilIdle()

        val loaded = assertIs<HelpListUiState.Loaded>(model.state.value)
        assertEquals(listOf("t-3", "t-2", "t-1"), loaded.tickets.map { it.id })
        assertEquals(listOf(HelpStatus.ANSWERED, HelpStatus.OPEN, HelpStatus.CLOSED), loaded.tickets.map { it.status })
        assertEquals(listOf(true, false, false), loaded.tickets.map { it.newReply })
        assertEquals(1, loaded.newReplies)
        assertEquals("The add button does nothing.", loaded.tickets.first().preview)
    }

    @Test
    fun `no questions is an empty list, not a failure`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { list = AuthResult.Ok(HelpTicketListDto(emptyList(), 0)) }
        val model = HelpListViewModel(repo)

        model.load()
        advanceUntilIdle()

        assertEquals(HelpListUiState.Loaded(emptyList(), 0), model.state.value)
    }

    @Test
    fun `a lost connection fails retryably and retry reads again through the loader`() = runTest(dispatcher) {
        val repo = FakeHelp()
        val model = HelpListViewModel(repo)
        model.load()
        advanceUntilIdle()
        assertEquals(HelpListUiState.Failed(HelpMapper.OFFLINE_KEY, retryable = true), model.state.value)

        repo.list = AuthResult.Ok(HelpTicketListDto(listOf(ticket()), 0))
        model.retry()
        assertEquals(HelpListUiState.Loading, model.state.value, "retry shows the loader, not the stale error")
        advanceUntilIdle()

        assertIs<HelpListUiState.Loaded>(model.state.value)
        assertEquals(2, repo.listReads)
    }

    @Test
    fun `a refusal carries the server's key and retryability`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { list = refused("auth.token.not_valid", retryable = false) }
        val model = HelpListViewModel(repo)

        model.load()
        advanceUntilIdle()

        assertEquals(HelpListUiState.Failed("auth.token.not_valid", retryable = false), model.state.value)
    }

    @Test
    fun `a pull keeps the list on screen until the answer and runs once at a time`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { list = AuthResult.Ok(HelpTicketListDto(listOf(ticket()), 0)) }
        val model = HelpListViewModel(repo)
        model.load()
        advanceUntilIdle()
        val before = model.state.value

        repo.gate = CompletableDeferred()
        repo.list = AuthResult.Ok(HelpTicketListDto(listOf(ticket("t-9", "answered", true)), 1))
        model.refresh()
        model.refresh()
        advanceUntilIdle()
        assertTrue(model.refreshing.value)
        assertEquals(before, model.state.value, "the old list stays while the pull is in flight")

        repo.gate?.complete(Unit)
        advanceUntilIdle()

        assertFalse(model.refreshing.value)
        assertEquals(1, assertIs<HelpListUiState.Loaded>(model.state.value).newReplies)
        assertEquals(2, repo.listReads, "the second pull was dropped, not queued")
    }

    @Test
    fun `a status this build does not know reads as with support rather than vanishing`() {
        val loaded =
            assertIs<HelpListUiState.Loaded>(
                HelpMapper.afterList(HelpTicketListDto(listOf(ticket(status = "escalated")), 0)),
            )

        assertEquals(HelpStatus.OPEN, loaded.tickets.single().status)
    }

    // ----- Ask a question ------------------------------------------------

    @Test
    fun `send is disabled until both fields hold something after trimming`() {
        val model = AskQuestionViewModel(FakeHelp())
        assertFalse(model.state.value.canSend)

        model.subject("   ")
        model.body("The add button does nothing.")
        assertFalse(model.state.value.canSend, "a blank subject is not a subject")

        model.subject("Cannot add a student")
        model.body(" \n ")
        assertFalse(model.state.value.canSend, "a blank question is not a question")

        model.body("The add button does nothing.")
        assertTrue(model.state.value.canSend)
    }

    @Test
    fun `typing stops at the server's lengths`() {
        val model = AskQuestionViewModel(FakeHelp())

        model.subject("s".repeat(HELP_SUBJECT_MAX + 10))
        model.body("b".repeat(HELP_BODY_MAX + 10))

        assertEquals(HELP_SUBJECT_MAX, model.state.value.subject.length)
        assertEquals(HELP_BODY_MAX, model.state.value.body.length)
        assertTrue(model.state.value.canSend)
        assertFalse(sendable("x".repeat(HELP_SUBJECT_MAX + 1), HELP_SUBJECT_MAX))
    }

    @Test
    fun `a sent question is trimmed, saved, and names the new question`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { asked = AuthResult.Ok(detail()) }
        val model = AskQuestionViewModel(repo)
        model.subject("  Cannot add a student ")
        model.body(" The add button does nothing.\n")

        repo.gate = CompletableDeferred()
        model.send()
        assertEquals(WriteState.Saving, model.state.value.write)
        assertFalse(model.state.value.canSend, "no second send while one is in flight")
        model.send()
        repo.gate?.complete(Unit)
        advanceUntilIdle()

        assertEquals(listOf("Cannot add a student" to "The add button does nothing."), repo.asks)
        assertEquals(WriteState.Saved, model.state.value.write)
        assertEquals("t-1", model.state.value.ticketId)
    }

    @Test
    fun `the daily limit maps to its own message, not retryable, keeping what was typed`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { asked = refused("help.ticket.too_many", retryable = false) }
        val model = AskQuestionViewModel(repo)
        model.subject("Cannot add a student")
        model.body("The add button does nothing.")

        model.send()
        advanceUntilIdle()

        assertEquals(WriteState.Failed("help.ticket.too_many", retryable = false), model.state.value.write)
        assertEquals("Cannot add a student", model.state.value.subject)
        assertEquals("The add button does nothing.", model.state.value.body)
        assertNull(model.state.value.ticketId)
    }

    @Test
    fun `a failed send keeps the text and the explicit retry sends the same question`() = runTest(dispatcher) {
        val repo = FakeHelp()
        val model = AskQuestionViewModel(repo)
        model.subject("Cannot add a student")
        model.body("The add button does nothing.")

        model.send()
        advanceUntilIdle()
        assertEquals(WriteState.Failed(HelpMapper.OFFLINE_KEY, retryable = true), model.state.value.write)
        assertTrue(model.state.value.canSend, "retry is one tap")

        repo.asked = AuthResult.Ok(detail())
        model.send()
        advanceUntilIdle()

        assertEquals(2, repo.asks.size)
        assertEquals(repo.asks[0], repo.asks[1], "the retry sends exactly what was typed")
        assertEquals(WriteState.Saved, model.state.value.write)
    }

    @Test
    fun `editing after a failure clears the stale error`() = runTest(dispatcher) {
        val model = AskQuestionViewModel(FakeHelp())
        model.subject("Cannot add a student")
        model.body("The add button does nothing.")
        model.send()
        advanceUntilIdle()

        model.body("The add button does nothing at all.")

        assertEquals(WriteState.Idle, model.state.value.write)
    }

    @Test
    fun `an invalid form sends nothing`() = runTest(dispatcher) {
        val repo = FakeHelp()
        val model = AskQuestionViewModel(repo)

        model.send()
        advanceUntilIdle()

        assertEquals(emptyList(), repo.asks)
        assertEquals(WriteState.Idle, model.state.value.write)
    }

    // ----- A thread ------------------------------------------------------

    @Test
    fun `a thread loads oldest first with support's messages marked`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { read = AuthResult.Ok(detail("answered", "requester", "support")) }
        val model = HelpThreadViewModel(repo)

        model.load("t-1")
        assertEquals(HelpThreadUiState.Loading, model.state.value)
        advanceUntilIdle()

        val thread = assertIs<HelpThreadUiState.Loaded>(model.state.value).thread
        assertEquals(listOf("m-0", "m-1"), thread.messages.map { it.id })
        assertEquals(listOf(false, true), thread.messages.map { it.fromSupport })
        assertFalse(thread.closed)
        assertEquals(listOf("t-1"), repo.reads)
    }

    @Test
    fun `a closed question says so`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { read = AuthResult.Ok(detail("closed", "requester", "support")) }
        val model = HelpThreadViewModel(repo)

        model.load("t-1")
        advanceUntilIdle()

        assertTrue(assertIs<HelpThreadUiState.Loaded>(model.state.value).thread.closed)
    }

    @Test
    fun `another account's question reads as not found, and retry reads again`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { read = refused("help.ticket.not_found", retryable = false) }
        val model = HelpThreadViewModel(repo)

        model.load("t-x")
        advanceUntilIdle()
        assertEquals(HelpThreadUiState.Failed("help.ticket.not_found", retryable = false), model.state.value)

        repo.read = AuthResult.TransportFailure
        model.retry()
        advanceUntilIdle()

        assertEquals(HelpThreadUiState.Failed(HelpMapper.OFFLINE_KEY, retryable = true), model.state.value)
        assertEquals(listOf("t-x", "t-x"), repo.reads)
    }

    @Test
    fun `a reply replaces the thread with the server's answer and empties the box`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { read = AuthResult.Ok(detail("closed", "requester", "support")) }
        val model = HelpThreadViewModel(repo)
        model.load("t-1")
        advanceUntilIdle()

        repo.replied = AuthResult.Ok(detail("open", "requester", "support", "requester"))
        model.type("  It works now, thank you. ")
        assertTrue(model.reply.value.canSend)
        model.send()
        assertEquals(WriteState.Saving, model.reply.value.write)
        advanceUntilIdle()

        assertEquals(listOf("t-1" to "It works now, thank you."), repo.replies)
        val thread = assertIs<HelpThreadUiState.Loaded>(model.state.value).thread
        assertEquals(3, thread.messages.size)
        assertFalse(thread.closed, "replying reopened it, as the server reported")
        assertEquals(ReplyUiState(), model.reply.value)
    }

    @Test
    fun `a failed reply keeps the text and the explicit retry sends it again`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { read = AuthResult.Ok(detail("answered", "requester", "support")) }
        val model = HelpThreadViewModel(repo)
        model.load("t-1")
        advanceUntilIdle()
        val before = model.state.value

        model.type("It works now, thank you.")
        model.send()
        advanceUntilIdle()

        assertEquals(WriteState.Failed(HelpMapper.OFFLINE_KEY, retryable = true), model.reply.value.write)
        assertEquals("It works now, thank you.", model.reply.value.text)
        assertEquals(before, model.state.value, "the thread is untouched by a failed reply")

        repo.replied = refused("help.ticket.not_found", retryable = false)
        model.send()
        advanceUntilIdle()
        assertEquals(WriteState.Failed("help.ticket.not_found", retryable = false), model.reply.value.write)

        repo.replied = AuthResult.Ok(detail("open", "requester", "support", "requester"))
        model.send()
        advanceUntilIdle()

        assertEquals(3, repo.replies.size)
        assertEquals(ReplyUiState(), model.reply.value)
    }

    @Test
    fun `typing after a failed reply clears the error, and a blank reply sends nothing`() = runTest(dispatcher) {
        val repo = FakeHelp().apply { read = AuthResult.Ok(detail()) }
        val model = HelpThreadViewModel(repo)
        model.load("t-1")
        advanceUntilIdle()

        model.type("   ")
        model.send()
        advanceUntilIdle()
        assertEquals(emptyList(), repo.replies)

        model.type("Hello")
        model.send()
        advanceUntilIdle()
        model.type("Hello again")

        assertEquals(WriteState.Idle, model.reply.value.write)

        model.type("r".repeat(HELP_BODY_MAX + 1))
        assertEquals(HELP_BODY_MAX, model.reply.value.text.length, "typing stops at the server's length")
    }

    @Test
    fun `nothing is sent or retried before a thread was opened`() = runTest(dispatcher) {
        val repo = FakeHelp()
        val model = HelpThreadViewModel(repo)

        model.type("Hello")
        model.send()
        model.retry()
        advanceUntilIdle()

        assertEquals(emptyList(), repo.replies)
        assertEquals(emptyList(), repo.reads)
        assertEquals(HelpThreadUiState.Loading, model.state.value)
    }
}
