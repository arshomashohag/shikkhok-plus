package com.shikkhokplus.app.core.designsystem

import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * Text sizes come from the type scale, not from a call site.
 *
 * **Why the scale test alone was not enough.** `TypographyScaleTest`
 * proves every theme slot is one of the design's seven steps, and a
 * screen can still write `bodyMedium.copy(fontSize = 15.sp)` and step
 * straight around it. Six call sites did — 15, 22 and 24sp, and an 18/28
 * under the Bangla line-height ratio — each a size the design never
 * checked against a Bangla conjunct. So a size literal is refused
 * anywhere but the scale itself.
 *
 * Letter spacing is not a size and stays allowed. `BrandHero.kt` is
 * allowed because its wordmark is the logo lockup, drawn the same way a
 * logo is, not text on the scale.
 */
class NoOffScaleTextSizeTest {

    private val sources = File("src/main/kotlin")

    private val allowed =
        setOf(
            "core/designsystem/Type.kt",
            "core/designsystem/BrandHero.kt",
        )

    private val sizeLiteral = Regex("""\b\d+(\.\d+)?\.sp\b""")

    @Test
    fun `no text size literal appears outside the type scale`() {
        assertTrue(sources.isDirectory, "Sources not found at $sources")
        val files = sources.walkTopDown().filter { it.extension == "kt" }.toList()
        assertTrue(files.isNotEmpty(), "No Kotlin sources found; this test would pass vacuously.")

        val offenders =
            files
                .filterNot { file -> allowed.any { file.invariantSeparatorsPath.endsWith(it) } }
                .flatMap { file ->
                    file.readLines().mapIndexedNotNull { index, line ->
                        val code = line.substringBefore("//")
                        val sized = sizeLiteral.containsMatchIn(code) && !code.contains("letterSpacing")
                        if (sized) "${file.name}:${index + 1}: ${line.trim()}" else null
                    }
                }

        assertTrue(
            offenders.isEmpty(),
            "Text sizes belong to the type scale (Type.kt). Use a typography slot or a named " +
                "role such as MoneyTotal, MoneyLead or BodyCompact:\n" + offenders.joinToString("\n"),
        )
    }

    @Test
    fun `every allowed file exists, so the allowlist cannot go stale`() {
        allowed.forEach { path ->
            assertTrue(File(sources, "com/shikkhokplus/app/$path").isFile, "Allowlisted file is gone: $path")
        }
    }
}
