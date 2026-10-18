package com.shikkhokplus.app.feature.auth

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The rules this surface must not break, asserted mechanically.
 *
 * The DEX scan and the merged-manifest allowlist arrive with the
 * packaging Bolt, which is the first thing that needs them. These are
 * the **source-level** half, available now and cheap: they catch the
 * reference on the commit that adds it rather than at the release
 * build.
 */
class AuthSurfaceRulesTest {

    private val moduleRoot = File("src/main")

    private fun sourceText(): String =
        File(moduleRoot, "kotlin").walkTopDown()
            .filter { it.extension == "kt" }
            .joinToString("\n") { it.readText() }

    /**
     * Every permission the manifest actually DECLARES.
     *
     * Parsed from `<uses-permission>` elements rather than matched as
     * free text: a first attempt at this matched the manifest's own
     * explanatory comment, which named AD_ID in order to forbid it. A
     * test that fails on the comment warning against a thing — while
     * saying nothing about the thing — is worse than no test, because
     * the obvious fix is to delete the warning.
     */
    private fun declaredPermissions(): List<String> {
        val manifest = File(moduleRoot, "AndroidManifest.xml").readText()
        return Regex("""<uses-permission[^>]*android:name="([^"]+)"""")
            .findAll(manifest)
            .map { it.groupValues[1] }
            .toList()
    }

    @Test
    fun `the manifest requests no SMS read permission`() {
        // OTP autofill uses the SMS Retriever API ONLY [TC-5]. The
        // Retriever needs no permission at all, which is the whole
        // reason it is the chosen mechanism.
        val declared = declaredPermissions()
        assertFalse(declared.any { it.contains("RECEIVE_SMS") })
        assertFalse(declared.any { it.contains("READ_SMS") })
        assertFalse(declared.any { it.contains("READ_PHONE_STATE") })
        assertFalse(declared.any { it.contains("READ_PHONE_NUMBERS") })
    }

    @Test
    fun `the manifest declares no advertising id permission`() {
        // AD_ID is the declaration Play's Families review looks for,
        // and a transitive ads or analytics SDK adds it silently via
        // manifest merger [TC-3, TC-6, D-37].
        //
        // This source manifest is only half the story -- the merged
        // RELEASE manifest is what Play reads, and the allowlist that
        // checks it arrives with the packaging Bolt. This catches the
        // declaration added by hand, on the commit that adds it.
        assertFalse(declaredPermissions().any { it.contains("AD_ID") })
    }

    @Test
    fun `the permission allowlist is empty at this bolt`() {
        // Stated as a number so a FIRST permission is a diff against
        // zero rather than a line appended to a growing list. INTERNET
        // arrives with the Bolt that first makes a real network call.
        assertEquals(emptyList(), declaredPermissions())
    }

    @Test
    fun `no source reads a device or SIM identifier`() {
        // The phone number is ALWAYS typed by the user [TC-4, D-35].
        // There is deliberately no code path that could read it.
        val forbidden = listOf(
            "TelephonyManager",
            "getLine1Number",
            "getSimSerialNumber",
            "getSubscriberId",
            "getImei",
            "getDeviceId",
            "ANDROID_ID",
            "AdvertisingIdClient",
            "getMacAddress",
            "getBSSID",
            "getSSID",
            "Build.getSerial",
        )
        val source = sourceText()
        val found = forbidden.filter { source.contains(it) }
        assertEquals(emptyList(), found, "forbidden identifier reference: $found")
    }

    @Test
    fun `both language bundles exist on screen one`() {
        // Bangla text that breaks a layout is a per-screen problem, and
        // discovering it on screen ONE is how it is not discovered on
        // screen forty [TC-15, D-43].
        assertTrue(File(moduleRoot, "res/values/strings.xml").exists())
        assertTrue(File(moduleRoot, "res/values-bn/strings.xml").exists())
    }

    @Test
    fun `every english string has a bangla counterpart`() {
        val names = { file: File ->
            Regex("""<string name="([^"]+)"""")
                .findAll(file.readText())
                .map { it.groupValues[1] }
                .toSet()
        }
        val english = names(File(moduleRoot, "res/values/strings.xml"))
        val bangla = names(File(moduleRoot, "res/values-bn/strings.xml"))

        assertEquals(
            emptySet(),
            english - bangla,
            "untranslated strings would render in English in a Bangla UI",
        )
    }

    @Test
    fun `the bangla bundle uses western numerals`() {
        // Matching the money-rendering decision: a teacher reading a
        // code from an SMS and typing it into this field must see the
        // same digits.
        val bangla = File(moduleRoot, "res/values-bn/strings.xml").readText()
        val banglaDigits = '০'..'৯'
        val found = bangla.filter { it in banglaDigits }
        assertEquals("", found, "Bangla-Indic numerals found: $found")
    }

    @Test
    fun `no user facing string is hardcoded in kotlin`() {
        // Everything user-facing lives in strings.xml. A literal here
        // is a string that can never be translated.
        val source = sourceText()
        val suspicious = Regex(""""[A-Z][a-z]+ [a-z]+ [a-z]+[.!?]"""")
            .findAll(source)
            .map { it.value }
            .toList()
        assertEquals(emptyList(), suspicious, "hardcoded UI text: $suspicious")
    }

    @Test
    fun `the lens hint travels out and decides nothing`() {
        // [D-2] allows the hint for UI shaping and forbids trusting it
        // for authorization. The client cannot grant itself a lens by
        // asking for one.
        assertEquals("X-Lens-Hint", LensHint.HEADER)
        assertEquals(LensHint.TEACHER, LensHint.fromWire("teacher"))
        assertEquals(null, LensHint.fromWire("superuser"))
    }

    @Test
    fun `no money type on this surface uses floating point`() {
        // U3 carries no money, but the ban is package-scoped rather
        // than a semantic judgement, so it is asserted here too.
        val source = sourceText()
        assertFalse(Regex("""\bval\s+\w*[Aa]mount\w*\s*:\s*(Double|Float)\b""")
            .containsMatchIn(source))
    }

    @Test
    fun `the composable branches only on state, never on a domain value`() {
        // team.md: "a composable that computes a fee balance is a bug".
        // Generalised: a composable receives a UiState and renders it
        // with NO conditional depending on a domain value [TC-9, D-31].
        //
        // This is the surface where such logic is hardest to see in
        // review -- `if (balance > 0) "Due" else "Paid"` is a business
        // rule about what counts as due, wearing presentation clothes.
        // Asserted mechanically rather than read, because the reviewer
        // on this surface has no declared Android experience.
        val screen = File(
            "src/main/kotlin/com/shikkhokplus/app/feature/auth/ui/AuthScreen.kt",
        ).readText()
        val body = screen.lines()
            .filterNot { it.trimStart().startsWith("*") }
            .filterNot { it.trimStart().startsWith("//") }
            .joinToString("\n")

        val comparisons = Regex("""\b(if|when)\s*\([^)]*(<|>|<=|>=)""")
            .findAll(body)
            .map { it.value }
            .toList()
        assertEquals(
            emptyList(),
            comparisons,
            "a comparison on a domain value appeared in the composable: $comparisons",
        )
    }

    @Test
    fun `the composable resolves a key and never renders server text`() {
        // Every user-facing string comes from a LOCAL resource named by
        // the server's message_key. A server-sent `message` could not be
        // localized and would show English in a Bangla UI [TC-15].
        //
        // A first version of this test matched the substring
        // "state.message" -- which `state.messageKey` contains -- and so
        // failed on the CORRECT code. It now asserts the positive
        // property: the key passes through MessageKeys.resolve, and the
        // DTO carries no plain `message` field for the screen to reach.
        val screen = File(
            "src/main/kotlin/com/shikkhokplus/app/feature/auth/ui/AuthScreen.kt",
        ).readText()
        assertTrue(
            screen.contains("MessageKeys.resolve(state.messageKey)"),
            "the screen must resolve the server's key to a local resource",
        )

        val dto = File(
            "src/main/kotlin/com/shikkhokplus/app/core/network/AuthDto.kt",
        ).readText()
        assertFalse(
            Regex("""val\s+message\s*:""").containsMatchIn(dto),
            "ErrorBody grew a plain `message` field; the server names a " +
                "string resource and never sends the text",
        )
    }
}
