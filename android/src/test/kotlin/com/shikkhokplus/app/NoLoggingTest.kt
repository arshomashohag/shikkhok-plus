package com.shikkhokplus.app

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * No log lines in the app [U3: NFR3.3].
 *
 * A username, a phone, an email, a password or a code that reaches
 * logcat is readable by anyone with the phone on a cable, and leaks into
 * bug reports. Three verifiers, all in CI's `android-unit` job: detekt's
 * `ForbiddenImport` refuses `android.util.Log` and the Ktor logging
 * plugin at the commit that imports them; this scan also catches what an
 * import rule cannot, a `println` or a fully qualified `android.util.Log`
 * call; and the last test keeps the detekt entries from being emptied.
 *
 * **Stated limit:** the scan is textual. A deliberately obfuscated call
 * (reflection, an alias) defeats it; that is left to review.
 */
class NoLoggingTest {

    private val sources = File("src/main/kotlin")
    private val detektConfig = File("detekt.yml")

    /** The expression NFR3.3 names; `\b` keeps `fingerprint(` from matching. */
    private val logging =
        Regex(
            """\bprintln\(|\bprint\(|android\.util\.Log|\bLog\.(v|d|i|w|e|wtf)\(|printStackTrace\(|""" +
                """io\.ktor\.client\.plugins\.logging""",
        )

    @Test
    fun `no source writes a log line`() {
        val files = sources.walkTopDown().filter { it.extension == "kt" }.toList()
        assertTrue(files.size > 20, "the Kotlin sources were not found; this test would pass vacuously")

        val offenders =
            files.flatMap { file ->
                file.readLines().mapIndexedNotNull { index, line ->
                    logging.find(line)?.let { "${file.path}:${index + 1}: ${it.value}" }
                }
            }

        assertEquals(emptyList(), offenders)
    }

    @Test
    fun `the expression matches what it is meant to, and not fingerprint`() {
        listOf("println(x)", "print(x)", "android.util.Log.d(t, m)", "Log.e(t, m)", "e.printStackTrace()").forEach {
            assertTrue(logging.containsMatchIn(it), it)
        }
        assertTrue(!logging.containsMatchIn("fingerprint(key)"))
        assertTrue(!logging.containsMatchIn("blueprint(x)"))
    }

    @Test
    fun `detekt still refuses both logging imports`() {
        val config = detektConfig.readText()

        assertTrue("- value: 'android.util.Log'" in config, "android.util.Log left detekt's ForbiddenImport")
        assertTrue(
            "- value: 'io.ktor.client.plugins.logging.*'" in config,
            "the Ktor logging plugin left detekt's ForbiddenImport",
        )
    }
}
