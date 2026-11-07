package com.shikkhokplus.app.feature.mfa

import android.content.SharedPreferences
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * The last two-step verification status the server sent this session.
 *
 * **Shared, so More can mark its row without asking.** More draws no
 * counts and makes no request of its own for a mark; the status is read
 * once when the session starts, for the offer, and again whenever the
 * two-step screen reads or changes it, and each read lands here. One per
 * session: a new sign-in starts with nothing known.
 */
class MfaStatusHolder {
    private val current = MutableStateFlow<MfaStatus?>(null)

    /** The status, or null before the first read answered. */
    val state: StateFlow<MfaStatus?> = current.asStateFlow()

    /**
     * Record what the server just said.
     *
     * @param status The status, as mapped
     */
    fun publish(status: MfaStatus) {
        current.value = status
    }
}

/**
 * Which accounts on this phone have answered the offer to turn on
 * two-step verification.
 */
interface MfaPromptStore {
    /**
     * Whether this account already answered.
     *
     * @param account The account id
     * @return True once it has
     */
    fun seen(account: String): Boolean

    /**
     * Remember that this account answered, Turn on or Not now alike.
     *
     * @param account The account id
     */
    fun markSeen(account: String)
}

/** Answers held in memory only, for tests and previews. */
class InMemoryMfaPromptStore : MfaPromptStore {
    private val answered = mutableSetOf<String>()

    override fun seen(account: String): Boolean = account in answered

    override fun markSeen(account: String) {
        answered += account
    }
}

/**
 * Answers in the app's own preferences file, as Settings keeps its own.
 *
 * **Plain, not encrypted**: one flag per account id, which names nobody
 * and holds no child's data. Kept across sign-out on purpose, so the
 * same person signing in again on the same phone is not asked twice.
 *
 * @param preferences The preferences file
 */
class PreferencesMfaPromptStore(private val preferences: SharedPreferences) : MfaPromptStore {
    override fun seen(account: String): Boolean = preferences.getBoolean(KEY_PREFIX + account, false)

    override fun markSeen(account: String) {
        preferences.edit().putBoolean(KEY_PREFIX + account, true).apply()
    }

    private companion object {
        const val KEY_PREFIX = "mfa_offer_answered_"
    }
}

/**
 * The one-time offer to turn on two-step verification, after signing in.
 *
 * **Offered only where the server recommends it** -- teachers and centre
 * members -- and only while it is off. Students and guardians are never
 * offered it; they find it in More like everyone else. Answering either
 * way, Turn on or Not now, is remembered for the account on this phone,
 * and More keeps its "Recommended" mark until it is on.
 *
 * A plain class rather than a ViewModel because it lives exactly as long
 * as one session's graph: a ViewModel would outlive a sign-out and carry
 * one account's answer into the next account's session.
 *
 * @property repository Reads the status
 * @property store Remembers who answered
 * @property holder Where the status is shared with More
 * @property account The signed-in account, read when asked
 */
class MfaPrompt(
    private val repository: MfaRepository,
    private val store: MfaPromptStore,
    private val holder: MfaStatusHolder,
    private val account: () -> String?,
) {
    /**
     * Read the status once and say whether to offer it.
     *
     * **Silent on failure.** Nobody asked for this read; an error about
     * it would be noise, and the offer simply waits for the next start.
     *
     * @return True to show the offer
     */
    suspend fun check(): Boolean {
        val result = repository.status() as? AuthResult.Ok ?: return false
        val status = MfaMapper.statusOf(result.value)
        holder.publish(status)
        val id = account()
        return MfaMapper.shouldPrompt(status, id, seen = id != null && store.seen(id))
    }

    /** Remember the answer, so the offer is not made again here. */
    fun answer() {
        account()?.let(store::markSeen)
    }
}
