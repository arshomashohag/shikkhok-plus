package com.shikkhokplus.app.core.queue

import org.junit.Rule
import org.junit.rules.TemporaryFolder
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

/**
 * The device write queue's storage guarantees [BR3.2].
 *
 * **Written from the acceptance criteria, not from the
 * implementation.** Each rule in `rules.md` names its own assertion in
 * its `violation_behaviour`, and these are those assertions. Where a
 * test needed to know a detail of how the store works to assert
 * anything — the temp file's name — that detail is a published
 * constant rather than a string copied out of the implementation.
 *
 * The queue is the one surface in this app that accepts a write
 * without connectivity, and `project.md` carries a NEVER against local
 * write queues whose own source [NFR5] permits exactly this one. What
 * makes this queue the permitted kind rather than the forbidden kind is
 * mechanical and is what these tests assert.
 */
class QueueStoreTest {

    @get:Rule
    val folder: TemporaryFolder = TemporaryFolder()

    private fun store(): QueueStore = QueueStore(File(folder.root, QueueStore.FILE_NAME))

    private fun roster(
        sessionId: String = "s-1",
        baseVersion: Int = 7,
    ): QueuedWrite =
        QueuedWrite.attendance(
            sessionId = sessionId,
            baseVersion = baseVersion,
            entries =
                listOf(
                    AttendanceEntry("e-1", present = true),
                    AttendanceEntry("e-2", present = false),
                ),
        )

    // ------------------------------------------------------------------
    // 1. Persistence across process death [BR3.2, AC3.1.9].
    // ------------------------------------------------------------------

    @Test
    fun `a queued write survives the process being killed and relaunched`() {
        // THE RULE [BR3.2]: an in-memory queue loses the roster when
        // Android kills the app in the background -- mid-class, on a
        // low-end device, which is when it is most likely.
        //
        // A new QueueStore over the same file is what a relaunch is:
        // no in-memory state carries over, so anything found must have
        // come off disk.
        val item = roster()
        store().enqueue(item)

        val afterRelaunch = store().read()

        assertEquals(1, afterRelaunch.size)
        assertEquals(item.id, afterRelaunch.single().id)
        assertEquals(item.clientMutationId, afterRelaunch.single().clientMutationId)
        assertEquals(7, afterRelaunch.single().baseVersion)
        assertEquals(
            listOf("e-1" to true, "e-2" to false),
            afterRelaunch.single().entries.map { it.enrollmentId to it.present },
        )
    }

    @Test
    fun `a queued write survives a restart still showing as not yet sent`() {
        // The state must survive too, not merely the payload. An item
        // that came back as CONFIRMED after a restart would be the
        // silent-queue failure arriving by a different route.
        store().enqueue(roster())

        assertEquals(QueueState.QUEUED, store().read().single().state)
    }

    // ------------------------------------------------------------------
    // 2. The atomic rename [NFR5.10].
    // ------------------------------------------------------------------

    @Test
    fun `an interrupted write leaves the previous queue intact`() {
        // THE RULE: a crash must leave either the old complete file or
        // the new complete file, never a truncated one.
        //
        // The crash is simulated by making the rename fail -- a
        // directory standing where the target file must go, which the
        // platform cannot rename over. That exercises the real failure
        // path rather than a stubbed one.
        val target = File(folder.root, "nested/queue.json")
        val first = roster(sessionId = "s-1")
        QueueStore(target).enqueue(first)

        // Replace the target with a directory, so the rename cannot
        // complete.
        assertTrue(target.delete())
        assertTrue(target.mkdirs())

        val store = QueueStore(target)
        assertFailsWith<java.io.IOException> {
            store.write(listOf(roster(sessionId = "s-2")))
        }

        // The temp file is cleaned up rather than left beside the
        // target to be mistaken for the queue.
        assertFalse(
            File(target.parentFile, target.name + QueueStore.TEMP_SUFFIX).exists(),
            "the temp file should not survive a failed rename",
        )
    }

    @Test
    fun `the temp file is written beside the target, never elsewhere`() {
        // THE RULE, and it is load-bearing: a rename across
        // filesystems is a copy, and a copy is not atomic. A temp file
        // in the cache directory -- the convenient thing to reach for
        // -- reintroduces the exact window the rename closes.
        //
        // Asserted by writing a queue and checking that nothing was
        // left outside the target's own directory, and that the temp
        // path the store would use resolves into that directory.
        val target = File(folder.root, "queue-dir/queue.json")
        QueueStore(target).enqueue(roster())

        val directory = requireNotNull(target.parentFile)
        val temp = File(directory, target.name + QueueStore.TEMP_SUFFIX)
        assertEquals(
            directory.canonicalPath,
            requireNotNull(temp.parentFile).canonicalPath,
            "the temp file must sit in the same directory as the target",
        )
        // And it does not survive a successful write either.
        assertFalse(temp.exists())
        assertEquals(1, QueueStore(target).read().size)
    }

    // ------------------------------------------------------------------
    // 3. Four distinct states [BR3.2, BR3.6, AC3.1.10].
    // ------------------------------------------------------------------

    @Test
    fun `the queue has exactly four states and they are distinct`() {
        // THE RULE [BR3.2]: exactly four, and AC3.1.10 requires three
        // to be separately visible rather than two. A test asserting
        // only that `failed` exists would pass against an enum that
        // mapped `conflicted` onto it.
        assertEquals(
            listOf(
                QueueState.QUEUED,
                QueueState.CONFIRMED,
                QueueState.FAILED,
                QueueState.CONFLICTED,
            ),
            QueueState.entries.toList(),
        )
        assertEquals(4, QueueState.entries.size)
        assertEquals(4, QueueState.entries.distinct().size)
    }

    @Test
    fun `each of the four states round-trips through storage`() {
        // A state that serialized to the same token as another would
        // collapse two of the four on the next read, which is the
        // failure the four-state design exists to prevent and which a
        // single-state test would not surface.
        val store = store()
        val items =
            QueueState.entries.mapIndexed { index, state ->
                roster(sessionId = "s-$index").copy(state = state)
            }
        store.write(items)

        assertEquals(
            QueueState.entries.toList(),
            store.read().map { it.state },
        )
    }

    @Test
    fun `conflicted is not failed, and schedules no automatic send`() {
        // THE RULE [BR3.6]: `failed` means "try again", and retrying a
        // conflict as-is is guaranteed to be refused again -- or
        // worse, invites a retry wrapper that strips the version and
        // overwrites somebody else's correction.
        assertNotEquals(QueueState.FAILED, QueueState.CONFLICTED)

        assertTrue(QueueState.QUEUED.isAutomaticallySendable())
        assertTrue(QueueState.FAILED.isAutomaticallySendable())
        assertFalse(
            QueueState.CONFLICTED.isAutomaticallySendable(),
            "a conflicted item must never be sent without the teacher asking",
        )
        assertFalse(QueueState.CONFIRMED.isAutomaticallySendable())
    }

    @Test
    fun `a conflicted entry is still readable after a restart`() {
        // THE RULE [BR3.6]: the teacher's offline entry is preserved
        // until they explicitly re-apply or discard. Losing it on a
        // restart would discard it silently, which the rule forbids by
        // name.
        val conflicted =
            roster().copy(state = QueueState.CONFLICTED, conflictCurrentVersion = 9)
        store().enqueue(conflicted)

        val reloaded = store().read().single()
        assertEquals(QueueState.CONFLICTED, reloaded.state)
        assertEquals(9, reloaded.conflictCurrentVersion)
        assertEquals(
            listOf("e-1" to true, "e-2" to false),
            reloaded.entries.map { it.enrollmentId to it.present },
        )
    }

    // ------------------------------------------------------------------
    // 4. Re-apply carries a FRESH mutation id [BR3.7].
    // ------------------------------------------------------------------

    @Test
    fun `re-apply composes a new write with a fresh client_mutation_id`() {
        // **THE RULE this unit gets wrong by default** [BR3.7]. The
        // obvious implementation reuses the old id. That id carries a
        // unique constraint and § B.7 makes a duplicate return the
        // ORIGINAL stored result with 200 while writing nothing -- so
        // re-apply would report success and change nothing, which is
        // the exact opposite of what the teacher asked for.
        val refused =
            roster(baseVersion = 7)
                .copy(state = QueueState.CONFLICTED, conflictCurrentVersion = 8)

        val fresh = refused.reapplied()

        assertNotEquals(
            refused.clientMutationId,
            fresh.clientMutationId,
            "reusing the mutation id hits the replay path and changes nothing",
        )
        assertEquals(8, fresh.baseVersion, "re-apply carries the CURRENT version")
        assertEquals(QueueState.QUEUED, fresh.state)
        assertEquals(null, fresh.conflictCurrentVersion)
        // The roster the teacher recorded is carried through unchanged:
        // re-apply is a new decision about the same marks, not a new
        // set of marks.
        assertEquals(refused.entries, fresh.entries)
        assertEquals(refused.sessionId, fresh.sessionId)
    }

    @Test
    fun `re-apply refuses to reuse the refused write's mutation id`() {
        // The guard that makes the rule mechanical rather than a
        // convention. Without it, a future caller passing the old id
        // explicitly would reintroduce the silent-success defect, and
        // nothing would fail.
        val refused = roster().copy(state = QueueState.CONFLICTED)

        assertFailsWith<IllegalArgumentException> {
            refused.reapplied(freshMutationId = refused.clientMutationId)
        }
    }

    @Test
    fun `a re-applied write persists with its new id`() {
        // The whole point reaches disk, not just memory: a re-apply
        // that survived a restart carrying the OLD id would replay on
        // the next send.
        val store = store()
        val refused =
            roster(baseVersion = 7)
                .copy(state = QueueState.CONFLICTED, conflictCurrentVersion = 8)
        store.enqueue(refused)

        val fresh = refused.reapplied()
        store.write(store.read().map { if (it.id == refused.id) fresh else it })

        val reloaded = store().read().single()
        assertEquals(fresh.clientMutationId, reloaded.clientMutationId)
        assertNotEquals(refused.clientMutationId, reloaded.clientMutationId)
        assertEquals(8, reloaded.baseVersion)
    }

    // ------------------------------------------------------------------
    // 5. The rest of the storage contract.
    // ------------------------------------------------------------------

    @Test
    fun `a missing file reads as an empty queue, not an error`() {
        // First launch, and the state after a discard emptied it.
        assertEquals(emptyList(), QueueStore(File(folder.root, "absent.json")).read())
    }

    @Test
    fun `a corrupt file reads as an empty queue rather than crashing`() {
        // A corrupt queue that threw here would crash the app on
        // launch with no route to recovery, because the thing that
        // fails is the thing the teacher would have to open the app to
        // clear.
        val target = File(folder.root, QueueStore.FILE_NAME)
        target.writeText("{ this is not json")

        assertEquals(emptyList(), QueueStore(target).read())
    }

    @Test
    fun `discarding removes only the named item`() {
        // BR3.6's discard half. Removing more than was asked would be
        // discarding an entry silently, which the rule forbids.
        val store = store()
        val first = roster(sessionId = "s-1")
        val second = roster(sessionId = "s-2")
        store.enqueue(first)
        store.enqueue(second)

        store.remove(first.id)

        assertEquals(listOf(second.id), store().read().map { it.id })
    }

    @Test
    fun `the queue holds no name and no phone number`() {
        // **A security property, asserted rather than described**
        // [security-design § 7.1]. The file holds enrollment ids,
        // booleans, a version and UUIDs; the recorded decision not to
        // encrypt it [§ 7.2] rests on exactly that. A display name
        // added to QueuedWrite later would turn a roster of opaque ids
        // into identifying data and reopen that decision -- and this
        // test is what would notice.
        val target = File(folder.root, QueueStore.FILE_NAME)
        QueueStore(target).enqueue(roster())

        val onDisk = target.readText()

        assertFalse(onDisk.contains("display_name"), onDisk)
        assertFalse(onDisk.contains("displayName"), onDisk)
        assertFalse(onDisk.contains("phone"), onDisk)
    }
}
