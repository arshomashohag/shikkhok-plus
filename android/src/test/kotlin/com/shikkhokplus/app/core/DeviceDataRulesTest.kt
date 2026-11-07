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
