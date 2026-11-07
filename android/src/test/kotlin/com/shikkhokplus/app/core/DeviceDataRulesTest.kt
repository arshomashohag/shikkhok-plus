package com.shikkhokplus.app.core

import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * What the platform may copy off this phone, asserted from the sources.
 *
 * Parsed as XML rather than matched as text, for the reason the manifest
 * tests give: the files explain themselves in comments that name the
 * very things they forbid.
 */
class DeviceDataRulesTest {

    private val main = File("src/main")

    private fun parse(file: File): Element {
        val factory = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
        return factory.newDocumentBuilder().parse(file).documentElement
    }

    private fun Element.children(tag: String): List<Element> {
        val nodes = getElementsByTagName(tag)
        return (0 until nodes.length).map { nodes.item(it) as Element }
    }

    private val application: Element
        get() = parse(File(main, "AndroidManifest.xml")).children("application").single()

    @Test
    fun `backup stays off and the extraction rules are referenced`() {
        // allowBackup="false" alone leaves device-to-device transfer ON
        // from Android 12 at this targetSdk [C-46].
        assertEquals("false", application.getAttributeNS(ANDROID_NS, "allowBackup"))
        assertEquals("@xml/data_extraction_rules", application.getAttributeNS(ANDROID_NS, "dataExtractionRules"))
        assertEquals("@xml/backup_rules", application.getAttributeNS(ANDROID_NS, "fullBackupContent"))
    }

    @Test
    fun `the pre-Android-12 rules exclude every domain too`() {
        val rules = parse(File(main, "res/xml/backup_rules.xml"))

        assertTrue(rules.children("include").isEmpty())
        val excluded = rules.children("exclude").filter { it.getAttribute("path") == "." }
        assertEquals(DOMAINS, excluded.map { it.getAttribute("domain") }.toSet())
    }

    @Test
    fun `nothing is copied to cloud backup or to a new phone`() {
        // Every domain, both paths, and no include anywhere: a store
        // added later is excluded without anyone remembering to list it.
        val rules = parse(File(main, "res/xml/data_extraction_rules.xml"))

        assertTrue(rules.children("include").isEmpty(), "an include would copy that path off the phone")
        for (path in listOf("cloud-backup", "device-transfer")) {
            val section = rules.children(path).single()
            val excluded = section.children("exclude").filter { it.getAttribute("path") == "." }
            assertEquals(DOMAINS, excluded.map { it.getAttribute("domain") }.toSet(), "$path must exclude every domain")
        }
    }

    @Test
    fun `a release build permits no cleartext to any host`() {
        // L-21: the main config is what every non-debug build ships.
        assertEquals("@xml/network_security_config", application.getAttributeNS(ANDROID_NS, "networkSecurityConfig"))
        assertEquals("", application.getAttributeNS(ANDROID_NS, "usesCleartextTraffic"))

        val config = parse(File(main, "res/xml/network_security_config.xml"))
        assertEquals("false", config.children("base-config").single().getAttribute("cleartextTrafficPermitted"))
        assertTrue(config.children("domain-config").isEmpty(), "no host is exempted in a release build")
    }

    @Test
    fun `a debug build permits cleartext only to the loopback hosts`() {
        // The same three ApiClient.isLoopback accepts. A wider list here
        // would let a debug build talk plaintext to the LAN.
        val config = parse(File("src/debug/res/xml/network_security_config.xml"))
        assertEquals("false", config.children("base-config").single().getAttribute("cleartextTrafficPermitted"))
        val exempt = config.children("domain-config").single()
        assertEquals("true", exempt.getAttribute("cleartextTrafficPermitted"))
        assertEquals(
            setOf("10.0.2.2", "localhost", "127.0.0.1"),
            exempt.children("domain").map { it.textContent.trim() }.toSet(),
        )
        assertTrue(exempt.children("domain").none { it.getAttribute("includeSubdomains") == "true" })
    }

    private companion object {
        const val ANDROID_NS = "http://schemas.android.com/apk/res/android"

        val DOMAINS =
            setOf(
                "root",
                "file",
                "database",
                "sharedpref",
                "external",
                "device_root",
                "device_file",
                "device_database",
                "device_sharedpref",
            )
    }
}
