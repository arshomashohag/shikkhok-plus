package com.shikkhokplus.app.feature.hubenquiry

import android.net.Uri
import com.shikkhokplus.app.feature.hublisting.report.ReportLink
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The App Link that opens the request form from a public page's "Ask to
 * join" link [H5]: the manifest claims exactly
 * `https://<app host>/ui/hub-enquiry` with `autoVerify`, in a filter of its
 * own beside the report link's, and only a link to that path on that host
 * is read as an enquiry link. The twin of `HubReportAppLinkTest`.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class HubEnquiryAppLinkTest {

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
    fun `the main activity claims the enquiry path on the app host with autoVerify, in its own filter`() {
        val claims =
            mainActivity.children("intent-filter").filter { filter ->
                filter.children("data").any { it.android("path") == EnquiryLink.PATH }
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
        assertEquals(listOf(EnquiryLink.PATH), data.mapNotNull { it.android("path").ifEmpty { null } })
    }

    @Test
    fun `the app links claim exactly the report and enquiry paths, nothing wider`() {
        val paths =
            mainActivity.children("intent-filter").flatMap { filter ->
                filter.children("data").flatMap { data ->
                    listOf("path", "pathPrefix", "pathPattern", "pathAdvancedPattern")
                        .mapNotNull { data.android(it).ifEmpty { null } }
                }
            }

        assertEquals(setOf(ReportLink.PATH, EnquiryLink.PATH), paths.toSet())
        assertEquals(2, paths.size)
    }

    @Test
    fun `a link to the enquiry path carries its owner and batch`() {
        val uri = Uri.parse("https://$HOST${EnquiryLink.PATH}?owner=rahima-apa&batch=$BATCH")

        val link = EnquiryLink.from(uri, HOST)
        assertEquals(EnquiryLink("rahima-apa", BATCH), link)
        assertEquals(EnquiryRecipient("rahima-apa", BATCH), link?.recipient)
        val ownerOnly = Uri.parse("https://$HOST${EnquiryLink.PATH}?owner=rahima-apa")
        assertEquals(EnquiryLink("rahima-apa", null), EnquiryLink.from(ownerOnly, HOST))
    }

    @Test
    fun `a malformed query is still an enquiry link, for the form to refuse`() {
        val uri = Uri.parse("https://$HOST${EnquiryLink.PATH}?batch=not-a-uuid")

        assertEquals(EnquiryLink(null, "not-a-uuid"), EnquiryLink.from(uri, HOST))
        assertNull(EnquiryLink(null, null).recipient)
        assertNull(EnquiryLink("rahima-apa", "not-a-uuid").recipient)
        assertNull(EnquiryLink("", null).recipient)
    }

    @Test
    fun `other paths, hosts and schemes are not an enquiry link`() {
        val query = "?owner=rahima-apa"
        listOf(
            "https://$HOST/ui/hub-report$query",
            "https://$HOST${EnquiryLink.PATH}s$query",
            "https://$HOST${EnquiryLink.PATH}/extra$query",
            "https://elsewhere.example${EnquiryLink.PATH}$query",
            "http://$HOST${EnquiryLink.PATH}$query",
        ).forEach { assertNull(EnquiryLink.from(Uri.parse(it), HOST), it) }
        assertNull(EnquiryLink.from(null, HOST))
        // Nor is an enquiry link read as a report link.
        assertNull(ReportLink.from(Uri.parse("https://$HOST${EnquiryLink.PATH}$query"), HOST))
    }

    private companion object {
        const val ANDROID_NS = "http://schemas.android.com/apk/res/android"
        const val HOST = "app.example"
        const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"
    }
}
