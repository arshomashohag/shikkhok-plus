package com.shikkhokplus.app.core.queue

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.io.File
import java.io.FileOutputStream

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
 * **No encryption, as a recorded decision** [security-design § 7.2].
 * The file holds enrollment ids, presence booleans, a version number
 * and UUIDs — no name, no phone number, no profile field, no token. The
 * refresh token is encrypted because it is a 30-day credential readable
 * via adb on a rooted phone; a queued roster is neither a credential
 * nor identifying without the server's enrollment mapping. Flagged for
 * the human in § 7.2 rather than decided here.
 *
 * **Not thread-safe by itself.** Every mutator reads, transforms and
 * writes the whole file, so two concurrent callers can lose one
 * another's change. The queue is driven from one place — [QueueSync]
 * and the screens it serves, all on the main dispatcher — so a lock
 * here would be guarding against a caller that does not exist. Stated
 * rather than assumed, because the next person to add a background
 * writer needs to know this.
 *
 * @property file Where the queue lives
 * @property json How items are serialized
 */
class QueueStore(
    private val file: File,
    private val json: Json = DEFAULT_JSON,
) {

    /**
     * Discard every queued write, when an account's session ends.
     *
     * **Only at sign-out or deletion, and never silently.** Unsent
     * attendance is the teacher's work; the profile says how many items
     * will be lost before sign-out runs this. It is called at all
     * because the queue belongs to the account that wrote it: left in
     * place, the next person to sign in on this phone would send the
     * previous account's rosters under their own token.
     */
    fun clear() {
        write(emptyList())
    }

    /**
     * Read every queued item, oldest first.
     *
     * **A missing file is an empty queue, not an error.** That is the
     * state on first launch, and after a discard emptied it.
     *
     * **An unreadable file is also an empty queue**, and this is the
     * one swallowed failure in the class. The alternative is worse: a
     * corrupt queue file that throws here would crash the app on launch
     * with no route to recovery, because the thing that fails is the
     * thing the teacher would have to open the app to clear. A
     * truncated file should be unreachable given the rename above; if
     * one is somehow reached, starting empty is the recoverable
     * outcome.
     *
     * @return The queued items, or an empty list
     */
    fun read(): List<QueuedWrite> {
        if (!file.exists()) return emptyList()
        return try {
            json.decodeFromString(QueueFile.serializer(), file.readText()).items
        } catch (_: Exception) {
            emptyList()
        }
    }

    /**
     * Replace the whole queue, atomically.
     *
     * The sequence is the contract and each step is required:
     * serialize, write to a temp file **beside** the target, flush the
     * bytes to storage, then rename over the target.
     *
     * @param items The items to persist, oldest first
     * @throws java.io.IOException If the rename does not succeed, which
     *   is surfaced rather than swallowed: a write the caller believes
     *   succeeded while the queue still holds the old roster is the
     *   silent failure this whole class exists to prevent
     */
    fun write(items: List<QueuedWrite>) {
        file.parentFile?.mkdirs()

        // Same directory as the target. A cross-filesystem rename is a
        // copy, and a copy is not atomic.
        val temp = File(file.parentFile, file.name + TEMP_SUFFIX)
        val encoded = json.encodeToString(QueueFile.serializer(), QueueFile(items = items))

        FileOutputStream(temp).use { stream ->
            stream.write(encoded.toByteArray(Charsets.UTF_8))
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
     * Append one item to the queue.
     *
     * @param item The write to enqueue
     * @return The queue as it now stands
     */
    fun enqueue(item: QueuedWrite): List<QueuedWrite> {
        val updated = read() + item
        write(updated)
        return updated
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
        return updated
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
        return updated
    }

    companion object {
        /** The on-disk format version. */
        const val FORMAT_VERSION: Int = 1

        /** The queue file's name inside the app's files directory. */
        const val FILE_NAME: String = "write-queue.json"

        /**
         * The temp file's suffix.
         *
         * Public so a test can assert the temp file sits beside the
         * target rather than inferring the path.
         */
        const val TEMP_SUFFIX: String = ".tmp"

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
