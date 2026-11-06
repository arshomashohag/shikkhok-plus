package com.shikkhokplus.app.core.session

import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.HttpAttendanceRepository
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.network.WorkspaceDto
import com.shikkhokplus.app.core.queue.AttendanceEntry
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.QueueTarget
import com.shikkhokplus.app.core.queue.QueuedWrite
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.test.runTest
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Which workspace the teacher screens act on: the choice, its header,
 * and the two places a switch must not leak across, offline copies and
 * queued writes.
 */
class WorkspaceTest {

    private val solo = WorkspaceDto("w-solo", "solo")
    private val centre = WorkspaceDto("w-centre", "centre", "Udayan Coaching")

    @Test
    fun `with nothing chosen the server's first workspace is in effect and no header is sent`() {
        val holder = WorkspaceHolder(InMemoryWorkspaceStore())
        holder.reconcile(listOf(solo, centre))

        assertNull(holder.current())
        assertEquals(solo, holder.effective())
    }

    @Test
    fun `a choice is kept and is what goes out`() {
        val store = InMemoryWorkspaceStore()
        val holder = WorkspaceHolder(store)
        holder.reconcile(listOf(solo, centre))

        holder.choose("w-centre")

        assertEquals("w-centre", holder.current())
        assertEquals(centre, holder.effective())
        assertEquals("w-centre", store.read())
        assertEquals("w-centre", WorkspaceHolder(store).current(), "the choice survives a restart")
    }

    @Test
    fun `a stored choice the server no longer offers is forgotten`() {
        val store = InMemoryWorkspaceStore("w-gone")
        val holder = WorkspaceHolder(store)

        holder.reconcile(listOf(solo))

        assertNull(holder.current())
        assertNull(store.read())
        assertEquals(solo, holder.effective())
    }

    @Test
    fun `signing out forgets the choice and the list`() {
        val holder = WorkspaceHolder(InMemoryWorkspaceStore("w-centre"))
        holder.reconcile(listOf(solo, centre))

        holder.clear()

        assertNull(holder.current())
        assertEquals(emptyList(), holder.offered.value)
    }

    @Test
    fun `offline copies are kept apart per workspace under the account`() {
        assertEquals("a-1", offlineScope("a-1", null))
        assertEquals("a-1/ws-w-centre", offlineScope("a-1", "w-centre"))
        assertNull(offlineScope(null, "w-centre"), "nothing is kept with nobody signed in")
    }

    private val ok = headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))

    @Test
    fun `every request names the chosen workspace and none is named without a choice`() = runTest {
        val seen = mutableListOf<String?>()
        var chosen: String? = null
        val engine =
            MockEngine { request ->
                seen += request.headers[WORKSPACE_HEADER]
                respond("{}", HttpStatusCode.OK, ok)
            }
        val client =
            ApiClient.build("https://staging.example", engine, TokenStore.InMemory(), workspace = { chosen })

        client.get("/v1/batches")
        chosen = "w-centre"
        client.get("/v1/batches")

        assertEquals(listOf(null, "w-centre"), seen)
    }

    @Test
    fun `a request that names its own workspace keeps it`() = runTest {
        val seen = mutableListOf<List<String>?>()
        val engine =
            MockEngine { request ->
                seen += request.headers.getAll(WORKSPACE_HEADER)
                respond("{}", HttpStatusCode.OK, ok)
            }
        val client =
            ApiClient.build("https://staging.example", engine, TokenStore.InMemory(), workspace = { "w-centre" })

        client.get("/v1/batches") { header(WORKSPACE_HEADER, "w-solo") }

        assertEquals(listOf<List<String>?>(listOf("w-solo")), seen)
    }

    @Test
    fun `a queued write is stamped with the workspace it was made in and replayed there`() = runTest {
        var chosen = "w-solo"
        val file = File.createTempFile("queue", ".json").apply { deleteOnExit() }
        val store = QueueStore(file, currentAccount = { "a-1" }, currentWorkspace = { chosen })

        val queued =
            store.enqueue(
                QueuedWrite(
                    id = "q-1",
                    target = QueueTarget.ATTENDANCE,
                    sessionId = "s-1",
                    baseVersion = 3,
                    clientMutationId = "m-1",
                    entries = listOf(AttendanceEntry(enrollmentId = "e-1", present = true)),
                ),
            ).single()
        assertEquals("w-solo", queued.workspaceId)

        // The teacher switches to the centre before the write is replayed.
        chosen = "w-centre"
        val seen = mutableListOf<List<String>?>()
        val engine =
            MockEngine { request ->
                seen += request.headers.getAll(WORKSPACE_HEADER)
                respond("""{"attendance_version":4,"submission_id":"sub-1"}""", HttpStatusCode.OK, ok)
            }
        val client =
            ApiClient.build("https://staging.example", engine, TokenStore.InMemory(), workspace = { chosen })
        HttpAttendanceRepository(client).submit(store.read().single())

        assertEquals(listOf<List<String>?>(listOf("w-solo")), seen)
    }

    @Test
    fun `a write already stamped keeps its workspace when queued again`() {
        val file = File.createTempFile("queue", ".json").apply { deleteOnExit() }
        val store = QueueStore(file, currentAccount = { "a-1" }, currentWorkspace = { "w-centre" })

        val queued =
            store.enqueue(
                QueuedWrite(
                    id = "q-2",
                    target = QueueTarget.TOPIC,
                    sessionId = "s-1",
                    baseVersion = 1,
                    clientMutationId = "m-2",
                    topic = "Motion",
                    workspaceId = "w-solo",
                ),
            ).single()

        assertEquals("w-solo", queued.workspaceId)
    }
}
