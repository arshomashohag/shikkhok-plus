package com.shikkhokplus.app

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The username reaches this client in exactly the shapes that carry it,
 * and no other [U3: NFR3.5, FR9].
 *
 * The username is owner-private: it arrives only in `MeResponse` and
 * `UsernameChangeResponse`, and is sent only in the requests that choose,
 * check or sign in with one. A DTO elsewhere declaring a `username` (or
 * a `login`) field is how a screen would start showing someone else's, so
 * any such declaration in `core/network` outside the allowlist fails. An
 * unannotated property is matched too, because it serializes under its
 * own name. The `MockEngine` URL assertions are the other half: they see
 * a value placed in a path or a query by string building, which no
 * declaration scan can.
 */
class UsernameDeclarationScanTest {

    private val network = File("src/main/kotlin/com/shikkhokplus/app/core/network")

    private val allowed =
        setOf(
            "MeDto",
            "UsernameChangeDto",
            "SignupRequestDto",
            "VerifyRequest",
            "UsernameAvailabilityRequest",
            "UsernameChangeRequest",
            "PasswordSignInRequest",
        )

    private val declaration =
        Regex("""@SerialName\("(?:username|login)"\)|\b(?:val|var)\s+(?:username|login)\b""")

    private val classStart = Regex("""\bclass\s+(\w+)""")

    /** Every declaring class: the nearest class declared above each match. */
    private fun declaringClasses(): Map<String, Set<String>> =
        network.walkTopDown().filter { it.extension == "kt" }.associate { file ->
            val text = file.readText()
            val classes = classStart.findAll(text).map { it.range.first to it.groupValues[1] }.toList()
            file.name to
                declaration.findAll(text).mapNotNull { match ->
                    classes.lastOrNull { it.first < match.range.first }?.second
                }.toSet()
        }.filterValues { it.isNotEmpty() }

    @Test
    fun `only the allowlisted shapes declare a username or a login`() {
        val found = declaringClasses()
        assertTrue(found.isNotEmpty(), "no declaration was found; the scan is not reading the sources")

        val outside = found.flatMap { (file, classes) -> (classes - allowed).map { "$file: $it" } }

        assertEquals(emptyList(), outside)
    }

    @Test
    fun `every allowlisted shape is still there, so the allowlist cannot rot`() {
        assertEquals(allowed, declaringClasses().values.flatten().toSet())
    }
}
