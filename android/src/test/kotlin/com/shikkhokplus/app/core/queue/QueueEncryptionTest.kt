package com.shikkhokplus.app.core.queue

import org.junit.Rule
import org.junit.rules.TemporaryFolder
import java.io.File
import java.security.GeneralSecurityException
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The write queue is encrypted at rest, and a queue that cannot be read
 * is reported rather than dropped [RC-8, C-46].
 *
 * **Written from the finding, not the implementation.** The queue held
 * attendance for minors in a plain JSON file while every other local
 * store was encrypted. The criteria: nothing identifying is readable on
 * disk; an earlier build's plaintext queue is migrated rather than lost,
 * because its writes carry client mutation ids the teacher is relying
 * on; and a queue the app cannot open tells the teacher so.
 *
 * The real [AesGcmQueueCipher] runs here with a software key, because
 * the Android Keystore does not exist on the JVM; the Keystore half is
 * the key's source only, and `QueueKeys` falls back to a software key
 * of exactly this kind.
 */
class QueueEncryptionTest {

    @get:Rule
    val folder: TemporaryFolder = TemporaryFolder()

    private val file: File
        get() = File(folder.root, QueueStore.FILE_NAME)

    private val key: SecretKey = newKey()

    private fun newKey(): SecretKey = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()

    private fun store(cipher: QueueCipher = AesGcmQueueCipher { key }): QueueStore =
        QueueStore(file, cipher, currentAccount = { ACCOUNT })

    private fun roster(sessionId: String = SESSION): QueuedWrite =
        QueuedWrite.attendance(
            sessionId = sessionId,
            baseVersion = 7,
            entries = listOf(AttendanceEntry(ENROLLMENT, present = true)),
        )

    /** The queue as the previous build wrote it: plain JSON. */
    private fun writePlaintext(contents: QueueFile) {
        file.writeText(QueueStore.DEFAULT_JSON.encodeToString(QueueFile.serializer(), contents))
    }

    @Test
    fun `nothing identifying is readable on disk`() {
        store().enqueue(roster())

        val onDisk = file.readBytes()
        val asText = String(onDisk, Charsets.ISO_8859_1)

        for (secret in listOf(ACCOUNT, SESSION, ENROLLMENT, "attendance", "client_mutation_id")) {
            assertFalse(asText.contains(secret), "'$secret' is readable in the queue file")
        }
        assertContentEquals(QueueStore.MAGIC, onDisk.copyOfRange(0, QueueStore.MAGIC.size))
    }

    @Test
    fun `a sealed queue survives a relaunch under the same key`() {
        val queued = store().enqueue(roster())

        assertEquals(queued.map { it.id }, store().read().map { it.id })
    }

    @Test
    fun `each write is sealed afresh, so two identical queues differ on disk`() {
        // A reused IV under GCM leaks the XOR of two plaintexts and the
        // authentication key; a fresh one per write is the contract.
        val first = store()
        first.write(listOf(roster()))
        val once = file.readBytes()
        first.write(first.read())

        assertFalse(once.contentEquals(file.readBytes()))
    }

    @Test
    fun `a plaintext queue from an earlier build is migrated, not dropped`() {
        val item = roster().copy(accountId = ACCOUNT)
        writePlaintext(QueueFile(items = listOf(item)))

        assertEquals(listOf(item.clientMutationId), store().read().map { it.clientMutationId })

        val asText = String(file.readBytes(), Charsets.ISO_8859_1)
        assertFalse(asText.contains(SESSION), "the plaintext is rewritten sealed on first read")
        assertEquals(listOf(item.id), store().read().map { it.id }, "and still reads afterwards")
        assertFalse(store().hasUnreadableWrites(), "a migration is not a loss")
    }

    @Test
    fun `migrating an old-format queue keeps it adoptable`() {
        // A version-1 file holds ownerless items, adopted by the first
        // account to sign in. Sealing it at the CURRENT version with
        // nobody signed in would strand them: an ownerless item in a
        // current-format file is handed to nobody.
        writePlaintext(QueueFile(version = 1, items = listOf(roster())))
        var signedIn: String? = null
        val queue = QueueStore(file, AesGcmQueueCipher { key }, currentAccount = { signedIn })

        assertEquals(listOf<String?>(null), queue.read().map { it.accountId }, "nobody signed in adopts nothing")
        assertFalse(String(file.readBytes(), Charsets.ISO_8859_1).contains(SESSION), "but it is sealed")

        signedIn = ACCOUNT
        assertEquals(listOf(ACCOUNT), queue.read().map { it.accountId })
    }

    @Test
    fun `a queue sealed under a lost key is reported, set aside, and never overwritten silently`() {
        store().enqueue(roster())

        // The key is gone: a Keystore reset, or a run that fell back to a
        // key held only in memory.
        val replacement = newKey()
        val other = store(AesGcmQueueCipher { replacement })

        assertEquals(emptyList(), other.read(), "the app still opens, with an empty queue")
        assertTrue(other.hasUnreadableWrites(), "and says records were lost")
        val aside = File(folder.root, QueueStore.FILE_NAME + QueueStore.UNREADABLE_SUFFIX)
        assertTrue(aside.exists(), "the unreadable file is kept, not replaced by the next write")

        other.enqueue(roster("next-class"))
        assertTrue(aside.exists())
        assertEquals(listOf("next-class"), other.read().map { it.sessionId }, "new writes still queue")

        val relaunchedKey = newKey()
        val relaunched = store(AesGcmQueueCipher { relaunchedKey })
        assertTrue(relaunched.hasUnreadableWrites(), "the notice outlives the process until acknowledged")

        relaunched.acknowledgeUnreadableWrites()
        assertFalse(relaunched.hasUnreadableWrites())
        assertFalse(aside.exists())
    }

    @Test
    fun `an altered queue file is refused rather than read`() {
        store().enqueue(roster())
        val bytes = file.readBytes()
        bytes[bytes.size - 1] = (bytes[bytes.size - 1].toInt() xor 1).toByte()
        file.writeBytes(bytes)

        assertEquals(emptyList(), store().read())
        assertTrue(store().hasUnreadableWrites())
    }

    @Test
    fun `a write that cannot be sealed fails loudly and leaves the previous queue intact`() {
        store().enqueue(roster())
        val broken =
            object : QueueCipher {
                override fun seal(plain: ByteArray): ByteArray = throw GeneralSecurityException("keystore gone")

                override fun open(sealed: ByteArray): ByteArray = AesGcmQueueCipher { key }.open(sealed)
            }

        assertFailsWith<java.io.IOException> { store(broken).enqueue(roster("lost")) }

        assertEquals(listOf(SESSION), store().read().map { it.sessionId })
    }

    @Test
    fun `the fallback cipher never writes plain text`() {
        // QueueKeys.cipher() on the JVM has no Keystore and so takes the
        // in-memory fallback: the path a phone with a broken Keystore runs.
        store(QueueKeys.cipher()).enqueue(roster())

        assertFalse(String(file.readBytes(), Charsets.ISO_8859_1).contains(SESSION))
    }

    private companion object {
        const val ACCOUNT = "0d6f3c55-2b1e-4c35-9a37-6c1f5d7c2a11"
        const val SESSION = "session-42"
        const val ENROLLMENT = "enrollment-7"
    }
}
