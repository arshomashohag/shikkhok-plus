package com.shikkhokplus.app.feature.hublisting.report

import android.net.Uri
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The App Link that opens the report screen from a hub page's "Report this
 * page" link: the manifest claims exactly `https://<app host>/ui/hub-report`
 * with `autoVerify`, the host is a placeholder set per build type, and only
 * a link to that path on that host is read as a report link.
 *
 * Parsed as XML rather than matched as text, as the other manifest tests
 * are, because the manifest explains itself in comments.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class HubReportAppLinkTest {

    private fun Element.children(tag: String): List<Element> {
        val nodes = getElementsByTagName(tag)
        return (0 until nodes.length).map { nodes.item(it) as Element }
    }

    private fun Element.android(name: String): String = getAttributeNS(ANDROID_NS, name)

    private val mainActivity: Element
        get() {
            val factory = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
            val manifest = factory.newDocumentBuilder().parse(File("src/main/AndroidManifest.xml")).documentElement
            return manifest.children("activity").single { it.android("name") == ".MainActivity" }
        }

    @Test
    fun `the main activity claims the report path on the app host with autoVerify`() {
        val claims =
            mainActivity.children("intent-filter").filter { filter ->
                filter.children("data").any { it.android("path") == ReportLink.PATH }
            }

        val filter = claims.single()
        assertEquals("true", filter.android("autoVerify"))
        assertEquals(listOf("android.intent.action.VIEW"), filter.children("action").map { it.android("name") })
        assertEquals(
            setOf("android.intent.category.DEFAULT", "android.intent.category.BROWSABLE"),
            filter.children("category").map { it.android("name") }.toSet(),
        )
        val data = filter.children("data")
        assertEquals(listOf("https"), data.mapNotNull { it.android("scheme").ifEmpty { null } })
        assertEquals(listOf("\${appLinkHost}"), data.mapNotNull { it.android("host").ifEmpty { null } })
        assertEquals(listOf(ReportLink.PATH), data.mapNotNull { it.android("path").ifEmpty { null } })
    }

    @Test
    fun `the launcher filter stays separate from the app link`() {
        val launcher =
            mainActivity.children("intent-filter").single { filter ->
                filter.children("category").any { it.android("name") == "android.intent.category.LAUNCHER" }
            }

        assertTrue(launcher.children("data").isEmpty())
        assertEquals("", launcher.android("autoVerify"))
    }

    @Test
    fun `every build type sets the app link host`() {
        val gradle = File("build.gradle.kts").readText()

        listOf("debug", "release").forEach { type ->
            assertTrue(
                Regex("""manifestPlaceholders\["appLinkHost"]""").containsMatchIn(block(gradle, "$type {")),
                "the $type build type sets no appLinkHost",
            )
        }
    }

    @Test
    fun `a link to the report path carries its kind and id`() {
        val uri = Uri.parse("https://$HOST${ReportLink.PATH}?kind=owner_listing&id=$OWNER")

        assertEquals(ReportLink("owner_listing", OWNER), ReportLink.from(uri, HOST))
    }

    @Test
    fun `a malformed query is still a report link, for the screen to refuse`() {
        val uri = Uri.parse("https://$HOST${ReportLink.PATH}?kind=media")

        assertEquals(ReportLink("media", null), ReportLink.from(uri, HOST))
        assertNull(ReportLink("media", null).target)
    }

    @Test
    fun `other paths, hosts and schemes are not a report link`() {
        val query = "?kind=owner_listing&id=$OWNER"
        listOf(
            "https://$HOST/ui/dues$query",
            "https://$HOST${ReportLink.PATH}/extra$query",
            "https://elsewhere.example${ReportLink.PATH}$query",
            "http://$HOST${ReportLink.PATH}$query",
        ).forEach { assertNull(ReportLink.from(Uri.parse(it), HOST), it) }
        assertNull(ReportLink.from(null, HOST))
    }

    /** The text of the block that opens at [opening], up to its closing brace. */
    private fun block(text: String, opening: String): String {
        val start = text.indexOf(opening)
        check(start >= 0) { "no block $opening" }
        var depth = 0
        for (i in start until text.length) {
            when (text[i]) {
                '{' -> depth++
                '}' -> if (--depth == 0) return text.substring(start, i)
            }
        }
        error("unclosed block $opening")
    }

    private companion object {
        const val ANDROID_NS = "http://schemas.android.com/apk/res/android"
        const val HOST = "app.example"
        const val OWNER = "6f1c2b0e-3a4d-4e5f-8a9b-0c1d2e3f4a5b"
    }
}
