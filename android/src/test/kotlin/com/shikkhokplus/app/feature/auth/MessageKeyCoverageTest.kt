package com.shikkhokplus.app.feature.auth

import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Every key the backend can emit renders a real string on this client.
 *
 * **This is the one cross-surface check in the project**, and it exists
 * because the gap it closes is invisible from either side alone. The
 * backend is correct when it names a key; the client is correct when it
 * falls back to a generic message. Together they produce an app that
 * shows "Something went wrong" for a specific, actionable error — which
 * looks like a working error message and is therefore never reported.
 *
 * The backend publishes `message-keys.json` and asserts it matches its
 * own raise sites; this reads the same file. Neither surface can drift
 * alone.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MessageKeyCoverageTest {

    private fun publishedKeys(): List<String> {
        val file = findRepoFile("message-keys.json")
        assertTrue(file.exists(), "message-keys.json not found at ${file.path}")

        // A deliberately tiny reader rather than a JSON dependency: the
        // file is a flat list of strings, and adding a parser to the
        // Android test classpath to read it would be the larger change.
        return Regex("\"([a-z0-9]+(?:\\.[a-z0-9_]+)+)\"")
            .findAll(file.readText())
            .map { it.groupValues[1] }
            .toList()
    }

    private fun findRepoFile(name: String): File {
        var dir: File? = File(System.getProperty("user.dir").orEmpty())
        while (dir != null) {
            val candidate = File(dir, name)
            if (candidate.exists()) return candidate
            dir = dir.parentFile
        }
        return File(name)
    }

    @Test
    fun `every published key maps to a specific string`() {
        val unmapped = publishedKeys().filterNot(MessageKeys::isKnown)

        assertEquals(
            emptyList(),
            unmapped,
            "the backend can emit these keys and this client has no string " +
                "for them, so each renders a generic fallback: $unmapped",
        )
    }

    @Test
    fun `the published list is not empty`() {
        // Guards the check itself: a reader that silently found nothing
        // would make the assertion above vacuously true, which is this
        // project's most common defect shape.
        assertTrue(publishedKeys().size >= 9, "found ${publishedKeys().size} keys")
    }

    @Test
    fun `every mapped key resolves to a real resource`() {
        val fallback =
            MessageKeys.resolve("definitely.not.a.real.key")

        MessageKeys.knownKeys.forEach { key ->
            val resolved = MessageKeys.resolve(key)
            assertTrue(resolved != 0, "$key resolved to no resource")
            if (key != "error.unexpected") {
                assertTrue(
                    resolved != fallback,
                    "$key resolves to the generic fallback rather than its own string",
                )
            }
        }
    }
}
