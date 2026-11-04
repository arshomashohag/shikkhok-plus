package com.shikkhokplus.app.core.designsystem

import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Colour literals live in the token files, not in screens.
 *
 * **Why this is a test and not a convention.** Before the status
 * tokens existed, five files each carried their own literal greens,
 * ambers and reds, and four of them were light-theme values drawn on
 * the dark theme too: Today's "short" ink at 1.86:1, the guardian
 * notice's edge at 1.39:1, the OTP border at 2.0:1 and the student
 * hero's caption at 1.3:1. Each looked right in the light theme, which
 * is the one anyone checks. A literal outside the token files has no
 * dark value and no contrast test, so it is refused here.
 */
class NoHardcodedColorTest {

    private val sources = File("src/main/kotlin")

    /**
     * The only files allowed a colour literal, each with its reason.
     *
     * `BrandHero.kt` is fixed artwork: the brand blue ground and its
     * figures are the same in both themes, the way a logo is.
     */
    private val allowed =
        setOf(
            "core/designsystem/Color.kt",
            "core/designsystem/StatusColors.kt",
            "core/designsystem/BrandHero.kt",
        )

    private val literal = Regex("""\bColor\(\s*0x""")

    @Test
    fun `no colour literal appears outside the token files`() {
        assertTrue(sources.isDirectory, "Sources not found at $sources")
        val files = sources.walkTopDown().filter { it.extension == "kt" }.toList()
        assertTrue(files.isNotEmpty(), "No Kotlin sources found; this test would pass vacuously.")

        val offenders =
            files
                .filterNot { file -> allowed.any { file.invariantSeparatorsPath.endsWith(it) } }
                .flatMap { file ->
                    file.readLines().mapIndexedNotNull { index, line ->
                        val code = line.substringBefore("//")
                        if (literal.containsMatchIn(code)) "${file.name}:${index + 1}: ${line.trim()}" else null
                    }
                }

        assertTrue(
            offenders.isEmpty(),
            "Colour literals belong in Color.kt or StatusColors.kt, with a dark value and a " +
                "contrast test. Add a token instead:\n" + offenders.joinToString("\n"),
        )
    }

    @Test
    fun `every allowed file exists, so the allowlist cannot go stale`() {
        allowed.forEach { path ->
            assertTrue(File(sources, "com/shikkhokplus/app/$path").isFile, "Allowlisted file is gone: $path")
        }
    }
}
