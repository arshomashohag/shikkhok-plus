package com.shikkhokplus.app.core.queue

import kotlinx.coroutines.test.runTest
import org.junit.Rule
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The queue belongs to the account that wrote it [FE-2].
 *
 * **Written from the acceptance criteria.** Two defects, one on each
 * side: ending a session one way cleared the queue silently, losing a
 * teacher's unsent attendance; ending it another way left the queue in
 * place for the next person to sign in on the phone to send under their
 * own token. The criteria are that one account's writes are never sent
 * under another's, and that an account's writes outlive its session and
 * drain when it signs back in.
 */
class QueueOwnershipTest {

    @get:Rule
    val folder: TemporaryFolder = TemporaryFolder()

    /** Who is signed in, as the token store would report it. */
    private var signedIn: String? = ACCOUNT_A

    private val file: File
        get() = File(folder.root, QueueStore.FILE_NAME)

    private fun store(): QueueStore = QueueStore(file, TestQueueCipher, currentAccount = { signedIn })

    private fun roster(sessionId: String): QueuedWrite =
        QueuedWrite.attendance(
            sessionId = sessionId,
            baseVersion = 7,
            entries = listOf(AttendanceEntry("e-1", present = true)),
        )

    /** Records what was sent, and under which account. */
    private inner class RecordingTransport : QueueTransport {
        val sentAs: MutableList<Pair<String?, String>> = mutableListOf()

        override suspend fun send(item: QueuedWrite): SendOutcome {
            sentAs += signedIn to item.sessionId
            return SendOutcome.Applied(item.baseVersion + 1)
        }
    }

    @Test
    fun `an account switch never sends the previous account's writes`() = runTest {
        // THE LEAK. A's session was refused at a cold start, so A never
        // signed out and nothing cleared the queue; B signs in on the
        // same phone and the drain starts under B's token.
        store().enqueue(roster("a-session"))
        signedIn = null
        signedIn = ACCOUNT_B
        val transport = RecordingTransport()

        QueueSync(store(), transport).drain()

        assertEquals(emptyList(), transport.sentAs)
        assertEquals(emptyList(), store().read(), "B sees none of A's writes")
    }

    @Test
    fun `an account's writes survive its session and drain when it signs back in`() = runTest {
        // THE SILENT LOSS. A session the server ended used to discard
        // the queue; now the writes wait for their own account.
        store().enqueue(roster("a-session"))
        signedIn = null
        signedIn = ACCOUNT_B
        store().enqueue(roster("b-session"))
        signedIn = ACCOUNT_A
        val transport = RecordingTransport()

        QueueSync(store(), transport).drain()

        assertEquals(listOf<Pair<String?, String>>(ACCOUNT_A to "a-session"), transport.sentAs)
        signedIn = ACCOUNT_B
        assertEquals(listOf("b-session"), store().read().map { it.sessionId }, "B's write is untouched")
    }

    @Test
    fun `a write is stamped with the account it was made under`() {
        store().enqueue(roster("a-session"))

        assertEquals(listOf(ACCOUNT_A), store().read().map { it.accountId })
        assertTrue(file.readText().contains(ACCOUNT_A), "the owner is on disk, not only in memory")
    }

    @Test
    fun `clearing at sign-out discards only that account's writes`() {
        store().enqueue(roster("a-session"))
        signedIn = ACCOUNT_B
        store().enqueue(roster("b-session"))

        store().clear()

        assertEquals(emptyList(), store().read())
        signedIn = ACCOUNT_A
        assertEquals(listOf("a-session"), store().read().map { it.sessionId })
    }

    @Test
    fun `a stale write of another account's item changes nothing`() {
        // `write` replaces the CURRENT account's items. A screen still
        // holding A's item after B signed in cannot alter it, or hand it
        // to B, by writing it back.
        store().enqueue(roster("a-session"))
        val aItem = store().read().single()
        signedIn = ACCOUNT_B

        store().write(listOf(aItem.copy(baseVersion = 9)))

        assertEquals(emptyList(), store().read())
        signedIn = ACCOUNT_A
        assertEquals(listOf(7), store().read().map { it.baseVersion })
    }

    @Test
    fun `a drain stops when the account changes under it`() = runTest {
        // A send takes seconds on a poor network; the session can end
        // and another begin meanwhile. Nothing read under A may be sent
        // once A is no longer the one signed in.
        store().enqueue(roster("a-1"))
        store().enqueue(roster("a-2"))
        val transport =
            object : QueueTransport {
                val sent = mutableListOf<String>()

                override suspend fun send(item: QueuedWrite): SendOutcome {
                    sent += item.sessionId
                    signedIn = ACCOUNT_B
                    return SendOutcome.Failed(null)
                }
            }

        QueueSync(store(), transport).drain()

        assertEquals(listOf("a-1"), transport.sent)
    }

    @Test
    fun `a queue written before items carried an account is adopted once, by the first account`() {
        // The upgrade path. A version-1 file holds items with no owner;
        // they go to the first account signed in after the upgrade --
        // overwhelmingly the teacher who wrote them -- rather than being
        // dropped silently, and the file is rewritten so it happens once.
        file.writeText(legacyQueue("legacy-session"))

        signedIn = null
        assertEquals(1, store().read().size, "nobody signed in adopts nothing")
        assertTrue(file.readText().contains("\"version\":1"), "and the file keeps its old version")

        signedIn = ACCOUNT_A
        assertEquals(listOf(ACCOUNT_A), store().read().map { it.accountId })

        signedIn = ACCOUNT_B
        assertEquals(emptyList(), store().read(), "adopted once, so B never sees it")
        signedIn = ACCOUNT_A
        assertEquals(listOf("legacy-session"), store().read().map { it.sessionId })
    }

    @Test
    fun `an ownerless item in a current-format file is handed to nobody`() {
        // Adoption is an upgrade step, not a standing rule: an item
        // written with nobody signed in must not be claimed by whoever
        // signs in next.
        signedIn = null
        store().enqueue(roster("nobody"))

        signedIn = ACCOUNT_A
        assertEquals(emptyList(), store().read())
    }

    /** A version-1 queue file, as the previous build wrote it. */
    private fun legacyQueue(sessionId: String): String =
        """{"version":1,"items":[{"id":"i-1","target":"attendance","session_id":"$sessionId",""" +
            """"base_version":7,"client_mutation_id":"m-1",""" +
            """"entries":[{"enrollment_id":"e-1","present":true}],"state":"queued"}]}"""

    private companion object {
        const val ACCOUNT_A = "0d6f3c55-2b1e-4c35-9a37-6c1f5d7c2a11"
        const val ACCOUNT_B = "7b0c9e2a-61d4-4f8e-b1a2-3c5d6e7f8091"
    }
}
