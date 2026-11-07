package com.shikkhokplus.app.core.queue

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.GeneralSecurityException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Seals the queue file's bytes at rest, and opens them again.
 *
 * **Why the queue is encrypted now** [RC-8, C-46]. The earlier decision
 * not to (security-design § 7.2) rested on the file holding only opaque
 * ids. It also holds the account id, the workspace, a class topic typed
 * by the teacher and which child was present -- attendance for minors,
 * on a phone a family may share. Every other local store in the app is
 * encrypted through the Android Keystore; this one now is too.
 *
 * An interface rather than one class so the storage guarantees in
 * [QueueStore] are testable on the JVM, where the Android Keystore does
 * not exist. **There is deliberately no plaintext implementation in the
 * app's own sources**: the only one lives in the test sources, so no
 * production construction can choose it.
 */
interface QueueCipher {
    /**
     * Encrypt and authenticate [plain].
     *
     * @param plain The serialized queue
     * @return The sealed bytes, which carry everything [open] needs
     * @throws GeneralSecurityException If the key cannot be used
     */
    fun seal(plain: ByteArray): ByteArray

    /**
     * Authenticate and decrypt bytes [seal] produced.
     *
     * @param sealed The bytes as stored
     * @return The serialized queue
     * @throws GeneralSecurityException If the bytes were not sealed
     *   under this key, or were altered since
     */
    fun open(sealed: ByteArray): ByteArray
}

/**
 * AES-256-GCM over the whole file, with a fresh IV per write.
 *
 * The same algorithm the token store and the offline copies use through
 * `MasterKey.KeyScheme.AES256_GCM`. Taken directly from `javax.crypto`
 * rather than through `EncryptedFile` because `EncryptedFile` binds the
 * ciphertext to the file's NAME -- and [QueueStore] writes a temp file
 * and renames it over the target, which is the crash-safety the queue
 * depends on [BR3.2]. A sealed temp file would then never open under
 * the target's name.
 *
 * Layout: one byte of IV length, the IV, then the GCM ciphertext with
 * its tag. The IV is chosen by the provider, which the Android Keystore
 * requires for an encryption key.
 *
 * @param key Supplies the key, asked on every call so a key the
 *   Keystore cannot hand out fails the call rather than construction
 */
class AesGcmQueueCipher(private val key: () -> SecretKey) : QueueCipher {
    override fun seal(plain: ByteArray): ByteArray {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        cipher.updateAAD(AAD)
        val iv = cipher.iv
        val body = cipher.doFinal(plain)
        return byteArrayOf(iv.size.toByte()) + iv + body
    }

    override fun open(sealed: ByteArray): ByteArray {
        val ivLength = sealed.firstOrNull()?.toInt() ?: throw GeneralSecurityException("empty queue file")
        if (ivLength !in MIN_IV..MAX_IV || sealed.size <= 1 + ivLength) {
            throw GeneralSecurityException("not a sealed queue file")
        }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(TAG_BITS, sealed, 1, ivLength))
        cipher.updateAAD(AAD)
        return cipher.doFinal(sealed, 1 + ivLength, sealed.size - 1 - ivLength)
    }

    private companion object {
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val TAG_BITS = 128
        const val MIN_IV = 12
        const val MAX_IV = 16

        /** Binds the ciphertext to its purpose, so no other sealed blob opens as a queue. */
        val AAD: ByteArray = "shikkhokplus.write-queue".toByteArray(Charsets.UTF_8)
    }
}

/** Where the queue's key comes from. */
object QueueKeys {
    /** The queue's own Keystore alias, separate from the security-crypto master key. */
    private const val ALIAS = "shikkhokplus.write-queue.v1"

    private const val KEY_BITS = 256

    /** The software key bits for the fallback; never stored. */
    private const val EPHEMERAL_ALGORITHM = "AES"

    /**
     * The cipher the app's queue uses.
     *
     * **A Keystore key when the phone has a working Keystore**, which
     * is every supported phone in practice: the key never leaves the
     * secure hardware or the Keystore daemon, so the file cannot be read
     * off the phone.
     *
     * **When the Keystore fails, an in-memory key for this process only**
     * -- the queue's version of the token store falling back to memory.
     * Writes are still sealed, never stored in plain text, and still
     * survive the screens and the drain within this run. What they do not
     * survive is the process: on the next launch the file no longer
     * opens, and [QueueStore] sets it aside and tells the teacher that
     * unsent records were lost, rather than dropping them silently.
     *
     * @return The cipher
     */
    fun cipher(): QueueCipher {
        val key =
            try {
                keystoreKey()
            } catch (_: GeneralSecurityException) {
                ephemeralKey()
            } catch (_: java.io.IOException) {
                ephemeralKey()
            } catch (_: java.security.ProviderException) {
                // How a Keystore in a bad state reports itself on some
                // releases: a RuntimeException, not a checked one.
                ephemeralKey()
            }
        return AesGcmQueueCipher { key }
    }

    /**
     * Load the queue's Keystore key, creating it on first use.
     *
     * The same parameters `MasterKey.KeyScheme.AES256_GCM` asks for:
     * AES-256, GCM, no padding, encrypt and decrypt.
     *
     * @return The key
     */
    private fun keystoreKey(): SecretKey {
        val store = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(
            KeyGenParameterSpec
                .Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(KEY_BITS)
                .build(),
        )
        return generator.generateKey()
    }

    /**
     * A key for this process only.
     *
     * @return A fresh AES-256 key held in memory
     */
    private fun ephemeralKey(): SecretKey =
        KeyGenerator.getInstance(EPHEMERAL_ALGORITHM).apply { init(KEY_BITS) }.generateKey()

    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
}
