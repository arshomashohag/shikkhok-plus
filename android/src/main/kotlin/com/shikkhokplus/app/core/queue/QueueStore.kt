package com.shikkhokplus.app.core.queue

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.security.GeneralSecurityException
import java.security.ProviderException

/**
 * The file's contents: a version tag and the items.
 *
 * The wrapper exists so the on-disk shape can change without the reader
 * having to guess which shape it is holding. A bare list would leave a
 * future format change indistinguishable from a corrupt file.
 *
 * @property version The on-disk format, bumped when the shape changes
 * @property items The queued writes, oldest first
 */
@Serializable
data class QueueFile(
    val version: Int = QueueStore.FORMAT_VERSION,
    val items: List<QueuedWrite> = emptyList(),
)

/**
 * The device write queue, persisted as a serialized file [BR3.2].
 *
 * **Storage is a serialized file with atomic rename — the human's
 * decision, not this code's.** Not Room, not SharedPreferences, and
 * specifically not a plain overwrite of the target file.
 *
 * **Why the rename, concretely.** A plain overwrite truncates the file
 * and then writes it; a process death in that window leaves a
 * truncated file, and the roster the teacher just marked is gone. That
 * is not a theoretical window — it is mid-class on a low-end device,
 * which is exactly when Android kills a backgrounded app and exactly
 * what the queue exists for [NFR5.1, AC3.1.9]. Writing to a temp file,
 * flushing it to the platter, and renaming it over the target makes the
 * swap a single filesystem operation: a crash leaves either the old
 * complete file or the new complete file, never a half-written one.
 *
 * **The temp file is in the SAME directory, and that is load-bearing.**
 * A rename across filesystems is not a rename at all — the platform
 * implements it as copy-then-delete, which reintroduces the exact
 * window the rename was chosen to close. Using the cache directory for
 * the temp file, which is the convenient thing to reach for, is how
 * that happens. [QueueStore] therefore derives the temp path from the
 * target's own parent and never takes it as a parameter.
 *
 * **[flush] is a separate step from [write], and not decoration.**
 * `renameTo` orders the directory entry; it does not order the file's
 * own contents. Without the `fsync`, a crash can leave the rename
 * durable and the bytes it points at not, which is a complete-looking
 * file full of nothing.
 *
 * **Encrypted at rest, like every other local store** [RC-8, C-46].
 * This reverses the earlier decision not to [security-design § 7.2],
 * which rested on the file holding only opaque ids: it also holds the
 * account and workspace ids, a topic the teacher typed, and which child
 * was present -- attendance for minors, on a phone a family may share.
 * The serialized queue is sealed by [cipher] and framed with [MAGIC];
 * the temp-file-and-rename sequence below is unchanged, which is why
 * the cipher is applied to bytes here rather than through
 * `EncryptedFile` (see [AesGcmQueueCipher]).
 *
 * **A plaintext file from an earlier build is migrated, not dropped.**
 * Its items carry client mutation ids the server deduplicates on, so
 * losing them would lose a roster the teacher believes is on its way.
 * It is read as before and immediately rewritten sealed, at its own
 * format version so a pending adoption (see `readAll`) still happens.
 * If that rewrite fails the plaintext stays and the next read retries.
 *
 * **A file that cannot be opened is set aside and reported, never
 * overwritten in silence.** The key can be lost while the file
 * survives -- a Keystore reset, or a run whose Keystore failed and
 * sealed under a key held only in memory (see [QueueKeys.cipher]). The
 * file is renamed beside the target and [hasUnreadableWrites] stays
 * true until the teacher has been told and [acknowledgeUnreadableWrites]
 * is called. Nothing in it can be recovered, but nobody is left
 * believing it was sent.
 *
 * **Not thread-safe by itself.** Every mutator reads, transforms and
 * writes the whole file, so two concurrent callers can lose one
 * another's change. The queue is driven from one place — [QueueSync]
 * and the screens it serves, all on the main dispatcher — so a lock
 * here would be guarding against a caller that does not exist. Stated
 * rather than assumed, because the next person to add a background
 * writer needs to know this.
 *
 * **Every item belongs to one account, and each account sees only its
 * own.** [read] returns the signed-in account's items and [write]
 * replaces only those, leaving every other account's untouched. Scoping
 * here rather than in each screen is the point: the drain, the
 * attendance and topic screens and the sign-out count all go through
 * these two calls, so none of them can be the one that forgets. The
 * defect this closes had two halves -- one way of ending a session
 * cleared the queue silently, and the other (a refused refresh at a
 * cold start) left it in place for the next person to sign in on the
 * phone to send under their own token.
 *
 * @property file Where the queue lives
 * @property cipher Seals the file at rest; required, so no construction
 *   can forget it
 * @property json How items are serialized
 * @property currentAccount The signed-in account, or null when nobody
 *   is. Read on every call, never cached, so an account change is seen
 *   by the very next read
 * @property currentWorkspace The chosen workspace, or null for the
 *   default; stamped on each write as it is queued
 */
class QueueStore(
    private val file: File,
    private val cipher: QueueCipher,
    private val json: Json = DEFAULT_JSON,
    val currentAccount: () -> String? = { null },
    val currentWorkspace: () -> String? = { null },
) {
    /** Set when this run found a file it could not read, even if setting it aside failed. */
    private var unreadableThisRun = false

    /**
     * Discard the signed-in account's queued writes, when it signs out
     * or is deleted.
     *
     * **Only at an explicit sign-out or deletion, and never silently.**
     * Unsent attendance is the teacher's work; the sign-out dialog says
     * how many items will be lost before this runs. A session the SERVER
     * ended does not call this: those items stay bound to their account
     * and drain when it signs back in.
     *
     * **Only this account's items.** Another account's unsent writes on
     * the same phone are not this account's to discard. That makes the
     * call order-sensitive: the caller runs it while the session still
     * holds its token, before clearing the token.
     */
    fun clear() {
        write(emptyList())
    }

    /**
     * Read the signed-in account's queued items, oldest first.
     *
     * **A missing file is an empty queue, not an error.** That is the
     * state on first launch, and after a discard emptied it.
     *
     * **An unreadable file is also an empty queue, and it is reported.**
     * A corrupt or unopenable queue file that threw here would crash the
     * app on launch with no route to recovery, because the thing that
     * fails is the thing the teacher would have to open the app to
     * clear. So it reads as empty -- but the file is set aside rather
     * than overwritten, and [hasUnreadableWrites] tells the app to say
     * that unsent records were lost.
     *
     * @return The current account's items, or an empty list
     */
    fun read(): List<QueuedWrite> {
        val account = currentAccount()
        return readAll(account).filter { it.accountId == account }
    }

    /**
     * Replace the signed-in account's queue, atomically.
     *
     * Items with no account are stamped with the current one, which is
     * how a newly composed write acquires its owner without any screen
     * having to supply it. Every other account's items are carried over
     * unchanged -- and an item in [items] that already belongs to another
     * account is ignored rather than stored, so a screen still holding a
     * previous account's item cannot alter it, or hand it to this one,
     * by writing it back.
     *
     * @param items The current account's items, oldest first
     * @throws java.io.IOException If the rename does not succeed
     */
    fun write(items: List<QueuedWrite>) {
        val account = currentAccount()
        val mine =
            items
                .filter { it.accountId == null || it.accountId == account }
                .map { it.copy(accountId = account) }
        val others = readAll(account).filter { it.accountId != account }
        persist(others + mine)
    }

    /**
     * Read every item in the file, whichever account it belongs to.
     *
     * **Where a queue written before items carried an account is
     * adopted, once.** Such a file is tagged with an older [QueueFile]
     * version and its items have no account. They are given to the
     * first account the app is signed in as after the upgrade, and the
     * file is rewritten at the current version so it happens exactly
     * once. The reasoning, since it is a judgement rather than a fact:
     *
     * - The previous build cleared the queue on every sign-out and every
     *   lapsed session, so its unsent items survive an upgrade only in
     *   the account that was signed in, or -- after a refresh the server
     *   refused at a cold start -- until the next sign-in. Either way the
     *   first account signed in afterwards is overwhelmingly the one that
     *   wrote them, typically the same teacher who updated the app.
     * - Discarding them instead would silently drop a teacher's unsent
     *   attendance on an app update, which is the failure the queue
     *   exists to prevent.
     * - The residual case -- a refused session, then a DIFFERENT person
     *   signing in before this build was installed -- is the defect this
     *   build closes, so it cannot recur; for the items already caught in
     *   it, the server still authorizes every write against the sender's
     *   own batches and refuses a roster for a session that account does
     *   not own.
     *
     * Adoption only ever happens on an old-format file. An item with no
     * account in a current-format file is never handed to anyone.
     *
     * @param account The account reading, or null when nobody is
     * @return Every item, oldest first
     */
    private fun readAll(account: String?): List<QueuedWrite> {
        val (stored, plaintext) = decode() ?: return emptyList()
        if (stored.version >= FORMAT_VERSION || account == null) {
            if (plaintext) migrate(stored)
            return stored.items
        }

        val adopted = stored.items.map { if (it.accountId == null) it.copy(accountId = account) else it }
        persist(adopted)
        return adopted
    }

    /**
     * Rewrite a plaintext file sealed, keeping its format version.
     *
     * **A failure leaves the plaintext in place**, and it is retried on
     * the next read: the items are still returned to the caller, and a
     * migration that dropped them because the rewrite failed would be
     * the silent loss this class exists to prevent.
     *
     * @param stored The plaintext file's contents
     */
    private fun migrate(stored: QueueFile) {
        try {
            persist(stored.items, stored.version)
        } catch (_: IOException) {
            // Still plaintext; the next read tries again.
        }
    }

    /**
     * Decode the file, or null when it is missing or unreadable.
     *
     * An unreadable file is set aside, see [setAside].
     *
     * @return The file's contents and whether an earlier build stored
     *   it in plain text, or null
     */
    private fun decode(): Pair<QueueFile, Boolean>? {
        // Not `exists()`: something that is not a file standing at the
        // path holds no queue to lose, and moving it aside would hide the
        // failure the next write must report.
        if (!file.isFile) return null
        return try {
            val bytes = file.readBytes()
            val sealed = bytes.size >= MAGIC.size && MAGIC.indices.all { bytes[it] == MAGIC[it] }
            val text =
                if (sealed) {
                    cipher.open(bytes.copyOfRange(MAGIC.size, bytes.size)).decodeToString()
                } else {
                    bytes.decodeToString()
                }
            json.decodeFromString(QueueFile.serializer(), text) to !sealed
        } catch (_: IOException) {
            setAside()
        } catch (_: GeneralSecurityException) {
            setAside()
        } catch (_: ProviderException) {
            setAside()
        } catch (_: IllegalArgumentException) {
            // SerializationException is an IllegalArgumentException.
            setAside()
        }
    }

    /**
     * Move an unreadable file out of the way, so no later write
     * replaces it unnoticed, and remember that it happened.
     *
     * @return Null, the empty queue the caller then reads
     */
    private fun setAside(): Pair<QueueFile, Boolean>? {
        unreadableThisRun = true
        if (!file.renameTo(asideFile())) file.delete()
        return null
    }

    /** The file an unreadable queue is moved to. */
    private fun asideFile(): File = File(file.parentFile, file.name + UNREADABLE_SUFFIX)

    /**
     * Whether queued writes were found that could not be read, and so
     * will never be sent.
     *
     * Checks the file now as well, so the answer is right on the first
     * call after launch, before any screen has read the queue.
     *
     * @return True until [acknowledgeUnreadableWrites] is called
     */
    fun hasUnreadableWrites(): Boolean {
        decode()
        return unreadableThisRun || asideFile().exists()
    }

    /** The teacher has been told; forget the unreadable file. */
    fun acknowledgeUnreadableWrites() {
        unreadableThisRun = false
        asideFile().delete()
    }

    /**
     * Replace the whole file, every account's items, atomically.
     *
     * The sequence is the contract and each step is required:
     * serialize, write to a temp file **beside** the target, flush the
     * bytes to storage, then rename over the target.
     *
     * @param items Every account's items, oldest first
     * @param version The format version to record: the current one,
     *   except when migrating an older file
     * @throws java.io.IOException If sealing or the rename does not
     *   succeed, which
     *   is surfaced rather than swallowed: a write the caller believes
     *   succeeded while the queue still holds the old roster is the
     *   silent failure this whole class exists to prevent
     */
    private fun persist(items: List<QueuedWrite>, version: Int = FORMAT_VERSION) {
        file.parentFile?.mkdirs()

        // Same directory as the target. A cross-filesystem rename is a
        // copy, and a copy is not atomic.
        val temp = File(file.parentFile, file.name + TEMP_SUFFIX)
        val encoded = json.encodeToString(QueueFile.serializer(), QueueFile(version = version, items = items))
        val sealed = seal(encoded)

        FileOutputStream(temp).use { stream ->
            stream.write(sealed)
            stream.flush()
            // Orders the CONTENTS. `renameTo` orders only the directory
            // entry, so without this a crash can leave a complete-looking
            // file whose bytes never reached storage.
            stream.fd.sync()
        }

        if (!temp.renameTo(file)) {
            temp.delete()
            throw java.io.IOException(
                "could not replace the queue file at ${file.path}; the " +
                    "previous queue is intact and nothing was written.",
            )
        }
    }

    /**
     * Seal the serialized queue and frame it for the file.
     *
     * @param encoded The serialized queue
     * @return [MAGIC] followed by the sealed bytes
     * @throws IOException If the key cannot be used, so a key failure
     *   reaches the caller the way a failed rename does
     */
    private fun seal(encoded: String): ByteArray =
        try {
            MAGIC + cipher.seal(encoded.toByteArray(Charsets.UTF_8))
        } catch (e: GeneralSecurityException) {
            throw IOException("could not seal the queue; the previous queue is intact.", e)
        } catch (e: ProviderException) {
            throw IOException("could not seal the queue; the previous queue is intact.", e)
        }

    /**
     * Append one item to the queue.
     *
     * @param item The write to enqueue
     * @return The queue as it now stands
     */
    fun enqueue(item: QueuedWrite): List<QueuedWrite> {
        // The workspace is fixed when the write is made: a switch before
        // the replay must not send it to another workspace.
        val stamped = if (item.workspaceId == null) item.copy(workspaceId = currentWorkspace()) else item
        val updated = read() + stamped
        write(updated)
        // Read back rather than echoed, so the caller sees each item
        // as stored -- stamped with its account.
        return read()
    }

    /**
     * Replace one item, matched on its device-local [QueuedWrite.id].
     *
     * Matched on the item id rather than the mutation id because
     * re-apply changes the mutation id by design [BR3.7], so a mutation
     * id is not a stable handle on the row the teacher is looking at.
     *
     * @param item The item to store in place of the one with its id
     * @return The queue as it now stands
     */
    fun replace(item: QueuedWrite): List<QueuedWrite> {
        val updated = read().map { if (it.id == item.id) item else it }
        write(updated)
        // Read back rather than echoed, so the caller sees each item
        // as stored -- stamped with its account.
        return read()
    }

    /**
     * Remove one item, matched on its device-local id.
     *
     * The discard half of BR3.6: a conflicted item leaves the queue
     * only when the teacher says so.
     *
     * @param itemId The item to drop
     * @return The queue as it now stands
     */
    fun remove(itemId: String): List<QueuedWrite> {
        val updated = read().filterNot { it.id == itemId }
        write(updated)
        // Read back rather than echoed, so the caller sees each item
        // as stored -- stamped with its account.
        return read()
    }

    companion object {
        /**
         * The on-disk format version.
         *
         * 2 added the owning account to every item. A version-1 file is
         * still read, and its items adopted once (see `readAll`).
         */
        const val FORMAT_VERSION: Int = 2

        /** The queue file's name inside the app's files directory. */
        const val FILE_NAME: String = "write-queue.json"

        /**
         * The temp file's suffix.
         *
         * Public so a test can assert the temp file sits beside the
         * target rather than inferring the path.
         */
        const val TEMP_SUFFIX: String = ".tmp"

        /** The suffix of a file set aside because it could not be read. */
        const val UNREADABLE_SUFFIX: String = ".unreadable"

        /**
         * The first bytes of a sealed file.
         *
         * An earlier build wrote plain JSON, which starts with `{`, so
         * the two are told apart without guessing.
         */
        val MAGIC: ByteArray = "SKQ1".toByteArray(Charsets.US_ASCII)

        /**
         * The serializer configuration.
         *
         * `ignoreUnknownKeys` so a queue written by a newer build does
         * not crash an older one on downgrade — the same reasoning
         * [ApiClient] applies to server responses [D-26].
         *
         * `isLenient` is false for the reason it is false there: a
         * lenient parser accepts shapes that should be rejected, and a
         * queue that silently reads a malformed item is a roster
         * silently altered.
         */
        val DEFAULT_JSON: Json = Json {
            ignoreUnknownKeys = true
            isLenient = false
            encodeDefaults = true
        }
    }
}
