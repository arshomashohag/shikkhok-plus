package com.shikkhokplus.app.core.model

import java.io.File
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * The package-wide floating-point ban on the client's shared model package.
 *
 * The value class is the primary mechanism: a `Double` cannot be assigned
 * where a [Money] is expected, and the compiler stops it with no custom rule
 * at all. This is the **backstop** — it catches a money-carrying model class
 * that declares a bare `Double` or `Float` field without going through
 * [Money] at all, which the compiler has no reason to object to.
 *
 * It is deliberately a *package-scoped* ban rather than a semantic
 * "money-carrying" judgement. Deciding which fields carry money is exactly
 * what an unfamiliar reviewer cannot reliably do, so the rule does not ask
 * anyone to: nothing in `core/model` may use a floating-point type.
 *
 * Detekt will carry the same rule once it arrives with the packaging Bolt.
 * This test exists now because the rule is needed from the first commit that
 * ships a model class, not from the Bolt that happens to install detekt.
 */
class NoFloatingPointTest {

    private val modelPackage = File("src/main/kotlin/com/shikkhokplus/app/core/model")

    private val forbidden = listOf(
        Regex("""\bDouble\b"""),
        Regex("""\bFloat\b"""),
        Regex("""\.toDouble\(\)"""),
        Regex("""\.toFloat\(\)"""),
    )

    @Test
    fun `no floating-point type appears in the shared model package`() {
        assertTrue(modelPackage.isDirectory, "Model package not found at $modelPackage")

        val sources = modelPackage.walkTopDown().filter { it.extension == "kt" }.toList()
        assertTrue(
            sources.isNotEmpty(),
            "No Kotlin sources found; this test would pass vacuously."
        )

        val offenders = mutableListOf<String>()
        for (file in sources) {
            file.readLines().forEachIndexed { index, line ->
                val code = line.substringBefore("//").substringBefore("*")
                for (pattern in forbidden) {
                    if (pattern.containsMatchIn(code)) {
                        offenders += "${file.name}:${index + 1}: $line"
                    }
                }
            }
        }

        assertTrue(
            offenders.isEmpty(),
            "Floating-point types are banned package-wide in core/model " +
                "(BR6.4). Money is a decimal-backed value class; a Double " +
                "cannot represent most decimal fractions exactly.\n" +
                offenders.joinToString("\n")
        )
    }
}
