package com.shikkhokplus.app.core.designsystem

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Every string with a placeholder is fetched with its arguments.
 *
 * **Found on a device, by a person using the build.** The signup
 * button read `Send code to %1$s` — the string declares a placeholder
 * and the call site fetched it with no argument, so Android rendered
 * the placeholder itself.
 *
 * No existing test could catch it. The Robolectric screen tests assert
 * on test tags, so they never read the rendered text, and a unit test
 * of the ViewModel never touches resources at all. This reads the
 * source and the bundles directly, the way `MessageKeyCoverageTest`
 * reads `message-keys.json`.
 *
 * It also checks the two bundles agree on how many arguments each
 * string takes, which is the same defect in a worse form: a mismatch
 * does not render oddly, it throws at format time — and only in the
 * locale nobody is testing in.
 */
class StringPlaceholderTest {

    private fun findRepoFile(name: String): File {
        var dir: File? = File(System.getProperty("user.dir").orEmpty())
        while (dir != null) {
            val candidate = File(dir, name)
            if (candidate.exists()) return candidate
            dir = dir.parentFile
        }
        return File(name)
    }

    private val stringEntry =
        Regex("""<string name="([^"]+)">((?:(?!</string>).)*)</string>""", RegexOption.DOT_MATCHES_ALL)

    /** `%1${'$'}s` and `%1${'$'}d` both count; `%%` is an escaped percent. */
    private val placeholder = Regex("""%(\d)\$[sd]""")

    private fun placeholderCounts(path: String): Map<String, Int> =
        stringEntry
            .findAll(findRepoFile(path).readText())
            .associate { m ->
                m.groupValues[1] to
                    placeholder.findAll(m.groupValues[2]).map { it.groupValues[1] }.toSet().size
            }

    private fun kotlinSources(): List<File> =
        findRepoFile("android/src/main/kotlin")
            .walkTopDown()
            .filter { it.isFile && it.extension == "kt" }
            .toList()

    @Test
    fun `a string with a placeholder is never fetched without arguments`() {
        val counts = placeholderCounts("android/src/main/res/values/strings.xml")
        // `stringResource(R.string.x)` with no comma before the close
        // paren: the single-argument overload.
        val bare = Regex("""stringResource\(\s*R\.string\.(\w+)\s*\)""")

        val offenders =
            kotlinSources().flatMap { file ->
                bare
                    .findAll(file.readText())
                    .map { it.groupValues[1] }
                    .filter { (counts[it] ?: 0) > 0 }
                    .map { "${file.name}: $it" }
            }

        assertEquals(
            emptyList(),
            offenders,
            "these strings declare a placeholder and are fetched without one, " +
                "so the placeholder renders literally on screen",
        )
    }

    @Test
    fun `both bundles agree on how many arguments each string takes`() {
        // A mismatch throws at format time rather than rendering
        // oddly, and only in the locale that has the extra argument --
        // so a Bangla-only crash ships while English looks fine.
        val en = placeholderCounts("android/src/main/res/values/strings.xml")
        val bn = placeholderCounts("android/src/main/res/values-bn/strings.xml")

        val disagreeing =
            en.keys
                .intersect(bn.keys)
                .filter { en[it] != bn[it] }
                .map { "$it: en=${en[it]} bn=${bn[it]}" }

        assertEquals(emptyList(), disagreeing, "placeholder count differs between bundles")
    }

    @Test
    fun `both bundles carry the same strings`() {
        // A key present in one bundle only is a missing translation in
        // the direction that matters: the app falls back to English
        // silently, in a Bangla-first product.
        val en = placeholderCounts("android/src/main/res/values/strings.xml").keys
        val bn = placeholderCounts("android/src/main/res/values-bn/strings.xml").keys

        assertEquals(emptySet(), en - bn, "strings missing from the Bangla bundle")
        assertEquals(emptySet(), bn - en, "strings present only in the Bangla bundle")
    }

    @Test
    fun `the scan actually found strings to check`() {
        // The guard this project applies to every other scanner: a
        // check that read nothing reports success. If the resource
        // path moves, this fails rather than passing silently.
        val counts = placeholderCounts("android/src/main/res/values/strings.xml")
        assertTrue(counts.size > 50, "expected the full bundle, found ${counts.size}")
        assertTrue(
            counts.values.any { it > 0 },
            "expected some strings to declare placeholders",
        )
        assertTrue(kotlinSources().size > 20, "expected the Kotlin sources to be found")
    }
}
