package com.shikkhokplus.app

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The forbidden-identifier set is enforced at commit time as well as at
 * release time, and both gates name the same set [TC-3, TC-4, D-35,
 * D-37; project.md Mandated].
 *
 * **Why a test and not only the config.** The audit found detekt's
 * `ForbiddenImport` configured with an EMPTY list [FE-12]: the rule was
 * active and caught nothing, so a `TelephonyManager` import could sit on
 * `main` until the release DEX scan found it on the build about to ship.
 * An empty list looks exactly like a populated one to anyone who reads
 * only `active: true`. These assertions make the two lists one fact.
 */
class ForbiddenIdentifiersTest {

    private val dexGate = File("release-gates.gradle.kts")
    private val detektConfig = File("detekt.yml")
    private val lintConfig = File("lint.xml")
    private val sources = File("src/main/kotlin")

    /**
     * Where each identifier the release DEX scan looks for is stopped at
     * commit time: the class that hosts it, banned as an import by
     * detekt, or [LINT_ONLY] where the host is imported legitimately and
     * only a call-level check can tell a forbidden read from a fine one.
     */
    private val commitTimeHost =
        mapOf(
            "getImei" to "android.telephony.TelephonyManager",
            "getSubscriberId" to "android.telephony.TelephonyManager",
            "getSimSerialNumber" to "android.telephony.TelephonyManager",
            "getLine1Number" to "android.telephony.TelephonyManager",
            "getMacAddress" to "android.net.wifi.WifiInfo",
            "getBSSID" to "android.net.wifi.WifiInfo",
            "getSSID" to "android.net.wifi.WifiInfo",
            "AdvertisingIdClient" to "com.google.android.gms.ads.identifier.AdvertisingIdClient",
            "android_id" to "android.provider.Settings.Secure",
            // `android.os.Build` is imported for `Build.VERSION`.
            "getSerial" to LINT_ONLY,
        )

    private fun dexIdentifiers(): Set<String> {
        val text = dexGate.readText()
        val block = text.substringAfter("val forbiddenIdentifiers = listOf(").substringBefore("\n)")
        return block
            .lines()
            .map { it.substringBefore("//").trim() }
            .mapNotNull { Regex("""^"([^"]+)",?$""").find(it)?.groupValues?.get(1) }
            .toSet()
    }

    private fun forbiddenImports(): Set<String> =
        Regex("""^\s*- value: '([^']+)'""", RegexOption.MULTILINE)
            .findAll(detektConfig.readText())
            .map { it.groupValues[1] }
            .toSet()

    @Test
    fun `every identifier the release scan looks for has a commit-time check`() {
        val dex = dexIdentifiers()
        assertTrue(dex.size > 1, "the DEX list was not found; this test would pass vacuously")

        assertEquals(
            dex,
            commitTimeHost.keys,
            "the release DEX scan and the commit-time map name different sets; " +
                "decide where a new identifier is caught at commit time",
        )
    }

    @Test
    fun `every hosting class is a forbidden import in detekt`() {
        val banned = forbiddenImports()
        val hosts = commitTimeHost.values.filter { it != LINT_ONLY }.toSet()

        assertEquals(emptySet(), hosts - banned, "hosts missing from detekt ForbiddenImport")
        assertTrue(
            Regex("""ForbiddenImport:\s*\n\s*active: true""").containsMatchIn(detektConfig.readText()),
            "ForbiddenImport must be active",
        )
    }

    @Test
    fun `a read detekt cannot ban by import is fatal in lint`() {
        assertTrue(
            lintConfig.readText().contains("""<issue id="HardwareIds" severity="fatal" />"""),
            "HardwareIds must stay fatal: it is the commit-time check for $LINT_ONLY identifiers",
        )
    }

    @Test
    fun `no source names a forbidden class, imported or fully qualified`() {
        // An import rule is bypassed by a fully qualified reference. Our
        // own source is small enough to check for the names outright.
        val files = sources.walkTopDown().filter { it.extension == "kt" }.toList()
        assertTrue(files.isNotEmpty(), "no Kotlin sources found; this test would pass vacuously")
        val names =
            forbiddenImports().map { it.removeSuffix(".*") } +
                "android.provider.Settings.Secure.ANDROID_ID"

        val offenders =
            files.flatMap { file ->
                file.readLines().mapIndexedNotNull { index, line ->
                    names.firstOrNull { it in line }?.let { "${file.name}:${index + 1}: $it" }
                }
            }

        assertEquals(emptyList(), offenders)
    }

    private companion object {
        const val LINT_ONLY = "lint HardwareIds"
    }
}
