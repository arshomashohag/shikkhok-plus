package com.shikkhokplus.app

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Passwords and codes are never put in saved state [U3: NFR3.4, L-20].
 *
 * Saved instance state is a Bundle the platform may write to disk, so a
 * password or a code in it outlives the screen. Two textual rules: no
 * `SavedStateHandle` in the feature packages that handle secrets, and no
 * `rememberSaveable` whose variable is named like a secret. The
 * `StateRestorationTester` tests on each password field are the
 * behavioural half.
 */
class NoSavedSecretsTest {

    private val sources = File("src/main/kotlin/com/shikkhokplus/app")

    // Name-based, so a secret held under a name outside this list passes
    // the scan; the StateRestorationTester tests on the password and code
    // screens are the behavioural half that does not depend on names.
    private val secretName = Regex("""(?i)password|passwd|pass|pwd|pin|confirm|current|code|otp|secret""")

    private fun kotlinIn(vararg dirs: String): List<File> =
        dirs.flatMap { dir -> File(sources, dir).walkTopDown().filter { it.extension == "kt" }.toList() }

    @Test
    fun `no SavedStateHandle where secrets are handled`() {
        val files = kotlinIn("feature/auth", "feature/account", "core/session")
        assertTrue(files.size > 10, "the sources were not found; this test would pass vacuously")

        val offenders = files.filter { "SavedStateHandle" in it.readText() }.map { it.path }

        assertEquals(emptyList(), offenders)
    }

    @Test
    fun `no rememberSaveable holds a value named like a secret`() {
        val files = sources.walkTopDown().filter { it.extension == "kt" }.toList()
        val declaration = Regex("""\b(?:var|val)\s+(\w+)\s*(?:by|=)\s*rememberSaveable\b""")

        val found =
            files.flatMap { file ->
                declaration.findAll(file.readText()).map { file.name to it.groupValues[1] }
            }
        assertTrue(found.isNotEmpty(), "no rememberSaveable was found at all; the scan is not reading the sources")

        assertEquals(emptyList(), found.filter { secretName.containsMatchIn(it.second) })
    }
}
