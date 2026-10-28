package com.shikkhokplus.app.core.queue

import com.shikkhokplus.app.core.network.ErrorEnvelope

/**
 * What the server said about one queued write.
 *
 * A closed set rather than a status code, so the sync loop maps an
 * outcome to a state without deciding anything: retryability is read,
 * never inferred from a status [TC-9].
 */
sealed interface SendOutcome {
    /**
     * The server applied it, or replayed it [BR3.8].
     *
     * A replay is an [Applied] too, deliberately: § B.7 makes a
     * duplicate `client_mutation_id` return the original stored result
     * with 200, and from the device's point of view the write is on the
     * server either way.
     *
     * @property resultingVersion The version the server now holds
     */
    data class Applied(val resultingVersion: Int) : SendOutcome

    /**
     * The server refused it: somebody else wrote first [BR3.3, BR3.6].
     *
     * @property currentVersion What the server says is current now, so
     *   a re-apply can be composed against it [BR3.7]
     * @property envelope The refusal, carrying its `message_key`
     */
    data class Conflicted(
        val currentVersion: Int,
        val envelope: ErrorEnvelope,
    ) : SendOutcome

    /**
     * The send did not succeed and retrying is the right remedy.
     *
     * @property envelope The server's refusal, or null when nothing
     *   arrived at all
     */
    data class Failed(val envelope: ErrorEnvelope?) : SendOutcome
}

/** Sends one queued write to the server. */
fun interface QueueTransport {
    /**
     * Send one item.
     *
     * @param item The write to send
     * @return What the server said
     */
    suspend fun send(item: QueuedWrite): SendOutcome
}

/**
 * Drains the queue when connectivity returns [BR3.1].
 *
 * **Automatic, with no action from the teacher.** BR3.1 requires a
 * queued write to sync by itself when the network comes back; a queue
 * that needed a button would leave the roster unsent precisely when the
 * teacher has stopped thinking about it.
 *
 * **And automatic for two of the four states only.** [QueueState] owns
 * that decision through `isAutomaticallySendable`, rather than this
 * loop testing states itself, because this is where an automatic retry
 * on a conflict gets added by accident [BR3.6]. Retrying a conflicted
 * item as-is is guaranteed to be refused again — the version it carries
 * is stale by definition — and the dangerous near-miss is a retry
 * wrapper that "helpfully" strips the version, which would overwrite
 * the correction somebody else made. A [QueueState.CONFLICTED] item
 * moves only when the teacher re-applies or discards it.
 *
 * **Confirmed items are dropped once seen.** Keeping them would grow
 * the file without bound and would also mean the screen had to filter
 * them out, which is a decision better not duplicated.
 *
 * @property store Where the queue lives
 * @property transport How an item reaches the server
 */
class QueueSync(
    private val store: QueueStore,
    private val transport: QueueTransport,
) {

    /**
     * Try to send everything that may be sent automatically.
     *
     * Items are attempted oldest first, which matters for the two
     * queued paths: two rosters for one session must reach the server
     * in the order the teacher recorded them, or the second's
     * `base_version` describes a state that never existed.
     *
     * **One failure does not stop the drain.** A failed item is marked
     * and the loop continues, because the next item may target a
     * different session and refusing to try it would make one dead
     * roster block every other.
     *
     * @return The queue as it stands afterwards
     */
    suspend fun drain(): List<QueuedWrite> {
        var queue = store.read()

        for (item in queue.filter { it.isAutomaticallySendable() }) {
            val updated = when (val outcome = transport.send(item)) {
                is SendOutcome.Applied -> null

                is SendOutcome.Conflicted ->
                    item.copy(
                        state = QueueState.CONFLICTED,
                        conflictCurrentVersion = outcome.currentVersion,
                    )

                is SendOutcome.Failed -> item.failed(outcome.envelope)
            }

            queue = if (updated == null) {
                // Applied: the server has it, so the device no longer
                // needs to. Dropped rather than marked CONFIRMED and
                // kept, which would grow the file without bound.
                store.remove(item.id)
            } else {
                store.replace(updated)
            }
        }

        return queue
    }

    /**
     * Re-apply a conflicted item, as a NEW write [BR3.7].
     *
     * The fresh `client_mutation_id` and the current version are
     * composed by [QueuedWrite.reapplied]; this replaces the refused
     * item with that new one, so the refused attempt does not linger
     * beside its own replacement.
     *
     * Re-applying something that is not conflicted is refused rather
     * than tolerated: it would mean the screen offered the control in a
     * state where it has no meaning.
     *
     * @param itemId The conflicted item the teacher chose to re-apply
     * @return The queue afterwards
     * @throws IllegalArgumentException If no such conflicted item exists
     */
    fun reapply(itemId: String): List<QueuedWrite> {
        val existing = store.read().firstOrNull { it.id == itemId }
        require(existing != null && existing.state == QueueState.CONFLICTED) {
            "re-apply applies to a conflicted item; '$itemId' is " +
                "${existing?.state ?: "absent"}."
        }

        val fresh = existing.reapplied()
        val updated = store.read().map { if (it.id == itemId) fresh else it }
        store.write(updated)
        return updated
    }

    /**
     * Discard a conflicted item, keeping what the server holds [BR3.6].
     *
     * The other half of the teacher's explicit choice. Nothing is
     * silently discarded: this runs only when they ask.
     *
     * @param itemId The item to drop
     * @return The queue afterwards
     */
    fun discard(itemId: String): List<QueuedWrite> = store.remove(itemId)
}

/** How often the foreground loop retries while something is waiting. */
val QUEUE_RETRY_INTERVAL_MS: Long = 30_000L

/**
 * Keep the queue draining for as long as the caller stays active.
 *
 * **The trigger [QueueSync] never had.** The drain was written and
 * tested and nothing called it, so a roster that failed to send, or was
 * recorded offline, stayed on the phone indefinitely -- while the
 * screen said it was saved there and would send by itself [BR3.1].
 *
 * Drains at once, then every [intervalMs] while an item can still be
 * sent automatically, and idles cheaply otherwise. It is run only while
 * the app is in the foreground and someone is signed in, so it never
 * wakes a closed app and never sends without a token.
 *
 * **A timer rather than a connectivity callback**, deliberately:
 * listening for the network needs `ACCESS_NETWORK_STATE`, and the
 * release manifest's permission allowlist is a decision rather than a
 * log. Within an open app the two differ by at most one interval.
 *
 * @param sync The drain
 * @param store The queue it drains
 * @param intervalMs The pause between attempts
 * @param delayMs How to wait; injected so a test runs in virtual time
 */
suspend fun keepDraining(
    sync: QueueSync,
    store: QueueStore,
    intervalMs: Long = QUEUE_RETRY_INTERVAL_MS,
    delayMs: suspend (Long) -> Unit = { kotlinx.coroutines.delay(it) },
) {
    while (true) {
        if (store.read().any { it.isAutomaticallySendable() }) {
            sync.drain()
        }
        delayMs(intervalMs)
    }
}
