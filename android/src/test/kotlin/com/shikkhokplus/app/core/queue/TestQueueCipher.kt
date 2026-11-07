package com.shikkhokplus.app.core.queue

/**
 * A cipher that seals nothing, for tests that assert on the file's text.
 *
 * **Test sources only, by design.** The app's own sources carry no
 * plaintext [QueueCipher], so no production construction of
 * [QueueStore] can choose one. The storage guarantees these tests
 * assert -- atomic rename, account scoping, adoption -- do not depend on
 * the cipher, and `QueueEncryptionTest` asserts the real one.
 */
object TestQueueCipher : QueueCipher {
    override fun seal(plain: ByteArray): ByteArray = plain

    override fun open(sealed: ByteArray): ByteArray = sealed
}
