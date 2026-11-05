package com.shikkhokplus.app.core.offline

import android.content.Context
import android.content.SharedPreferences
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement

/** Where offline copies are kept: text by key. */
interface OfflineStore {
    /**
     * The text kept under [key], or null.
     *
     * @param key The key
     * @return The text, or null
     */
    fun get(key: String): String?

    /**
     * Keep [value] under [key], replacing what was there.
     *
     * @param key The key
     * @param value The text
     */
    fun put(key: String, value: String)

    /**
     * Forget [key].
     *
     * @param key The key
     */
    fun remove(key: String)

    /** Forget everything. */
    fun clear()
}

/** A store in memory only, for tests and for a phone whose keystore fails. */
class InMemoryOfflineStore : OfflineStore {
    private val values = mutableMapOf<String, String>()

    override fun get(key: String): String? = values[key]

    override fun put(key: String, value: String) {
        values[key] = value
    }

    override fun remove(key: String) {
        values.remove(key)
    }

    override fun clear() {
        values.clear()
    }
}

/**
 * A store in an encrypted preferences file.
 *
 * **Encrypted at rest through the Android Keystore**, as the tokens are
 * [RC-8]: these copies hold children's names, marks and fees, on a phone
 * a family may share.
 *
 * @param preferences The encrypted file
 */
class EncryptedOfflineStore private constructor(private val preferences: SharedPreferences) : OfflineStore {
    override fun get(key: String): String? = preferences.getString(key, null)

    override fun put(key: String, value: String) {
        preferences.edit().putString(key, value).apply()
    }

    override fun remove(key: String) {
        preferences.edit().remove(key).apply()
    }

    override fun clear() {
        preferences.edit().clear().apply()
    }

    companion object {
        private const val FILE_NAME = "offline_copies"

        /**
         * Build the store, falling back to memory when the keystore fails:
         * the app then keeps copies for the session only, never in plain
         * text.
         *
         * @param context The application context
         * @return An encrypted store, or an in-memory one
         */
        fun create(context: Context): OfflineStore =
            try {
                val masterKey =
                    androidx.security.crypto.MasterKey
                        .Builder(context)
                        .setKeyScheme(androidx.security.crypto.MasterKey.KeyScheme.AES256_GCM)
                        .build()
                EncryptedOfflineStore(
                    androidx.security.crypto.EncryptedSharedPreferences.create(
                        context,
                        FILE_NAME,
                        masterKey,
                        androidx.security.crypto.EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                        androidx.security.crypto.EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
                    ),
                )
            } catch (_: Exception) {
                InMemoryOfflineStore()
            }
    }
}

/**
 * One saved copy: when it was read, and what the server said.
 *
 * @property savedAt When this phone read it, in phone-clock milliseconds
 * @property value The server's response, as it arrived
 */
@Serializable
private data class SavedCopy(val savedAt: Long, val value: JsonElement)

/**
 * The last thing the server said, kept so a screen opened without a
 * connection shows it rather than an error.
 *
 * **Always overwritten when online.** Every successful read replaces
 * the copy; a copy is only ever read back when no answer arrived at all.
 * A refusal deletes it, since the person may no longer be allowed to see
 * it. It is returned as `Ok` carrying `savedAt`, so a screen knows to
 * mark it offline and to withhold what needs the server [TC-8].
 *
 * **Per account.** Copies are keyed by the signed-in account, so a
 * second person signing in on the same phone never sees the first one's,
 * and sign-out clears them all.
 *
 * @param store Where copies are kept
 * @param account The signed-in account, or null to keep nothing
 * @param json The same strict settings the network reads with
 * @param clock The phone's clock
 */
class OfflineCopies(
    private val store: OfflineStore,
    private val account: () -> String?,
    private val json: Json = ApiClient.json,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    /**
     * Read through the copy kept under [key].
     *
     * @param key What this read is, unique per screen and seat
     * @param serializer How the response is written down
     * @param fetch The read itself
     * @return The server's answer, or the saved copy when none arrived
     */
    suspend fun <T> through(
        key: String,
        serializer: KSerializer<T>,
        fetch: suspend () -> AuthResult<T>,
    ): AuthResult<T> {
        val result = fetch()
        val slot = account()?.let { "$it/$key" } ?: return result
        when (result) {
            is AuthResult.Ok ->
                store.put(
                    slot,
                    json.encodeToString(
                        SavedCopy.serializer(),
                        SavedCopy(clock(), json.encodeToJsonElement(serializer, result.value)),
                    ),
                )
            is AuthResult.Refused -> store.remove(slot)
            AuthResult.TransportFailure -> return saved(slot, serializer) ?: result
        }
        return result
    }

    /** Forget every copy, for sign-out and account deletion. */
    fun clear() {
        store.clear()
    }

    private fun <T> saved(slot: String, serializer: KSerializer<T>): AuthResult<T>? {
        val text = store.get(slot) ?: return null
        return try {
            val copy = json.decodeFromString(SavedCopy.serializer(), text)
            AuthResult.Ok(json.decodeFromJsonElement(serializer, copy.value), savedAt = copy.savedAt)
        } catch (_: SerializationException) {
            // A copy an older build wrote in another shape: forget it.
            store.remove(slot)
            null
        } catch (_: IllegalArgumentException) {
            store.remove(slot)
            null
        }
    }
}
