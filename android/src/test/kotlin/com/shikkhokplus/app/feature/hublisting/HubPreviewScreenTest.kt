package com.shikkhokplus.app.feature.hublisting

import android.webkit.WebResourceRequest
import android.webkit.WebView
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import com.shikkhokplus.app.feature.hublisting.ui.HubPreviewActions
import com.shikkhokplus.app.feature.hublisting.ui.HubPreviewScreen
import com.shikkhokplus.app.feature.hublisting.ui.PREVIEW_BASE_URL
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_PREVIEW_FRAME
import com.shikkhokplus.app.feature.hublisting.ui.configurePreviewWebView
import com.shikkhokplus.app.feature.hublisting.ui.hubPreviewLocaleTag
import com.shikkhokplus.app.feature.hublisting.ui.loadPreview
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** The preview screen and the WebView it shows the server's page in. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class HubPreviewScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun webView() = WebView(ApplicationProvider.getApplicationContext())

    @Test
    fun `the preview webview runs no script, reads no file and follows no link`() {
        val view = webView()

        configurePreviewWebView(view)

        assertFalse(view.settings.javaScriptEnabled)
        assertFalse(view.settings.allowFileAccess)
        assertFalse(view.settings.allowContentAccess)
        assertFalse(view.settings.javaScriptCanOpenWindowsAutomatically)
        val client = shadowOf(view).webViewClient
        val link =
            object : WebResourceRequest {
                override fun getUrl() = android.net.Uri.parse("https://site.example/hub/en")

                override fun isForMainFrame() = true

                override fun isRedirect() = false

                override fun hasGesture() = true

                override fun getMethod() = "GET"

                override fun getRequestHeaders() = emptyMap<String, String>()
            }
        assertTrue(client.shouldOverrideUrlLoading(view, link), "a clicked link is ignored, never loaded")
    }

    @Test
    fun `the page is loaded as the servers html on a base that grants no file access`() {
        val view = webView()

        loadPreview(view, "<p>page</p>")

        val loaded = shadowOf(view).lastLoadDataWithBaseURL
        assertEquals("about:blank", PREVIEW_BASE_URL)
        assertEquals(PREVIEW_BASE_URL, loaded.baseUrl)
        assertEquals("<p>page</p>", loaded.data)
        assertEquals("text/html", loaded.mimeType)
        assertEquals("UTF-8", loaded.encoding)
    }

    @Test
    fun `a ready preview shows the frame and the language chips switch it`() {
        val picked = mutableListOf<String>()
        compose.setContent {
            HubPreviewScreen(
                HubPreviewState(locale = "en", body = HubPreviewUiState.Ready("<p>page</p>")),
                HubPreviewActions(onLocale = { picked += it }),
            )
        }

        compose.onNodeWithTag(TAG_HUB_PREVIEW_FRAME).assertExists()
        compose.onNodeWithTag(hubPreviewLocaleTag("en")).assertIsSelected()
        compose.onNodeWithTag(hubPreviewLocaleTag("bn")).performClick()
        assertEquals(listOf("bn"), picked)
    }

    @Test
    fun `a failed preview shows the message with retry and no frame`() {
        var retried = 0
        compose.setContent {
            HubPreviewScreen(
                HubPreviewState(locale = "en", body = HubPreviewUiState.Error(HUB_OFFLINE_KEY, retryable = true)),
                HubPreviewActions(onRetry = { retried++ }),
            )
        }

        compose.onNodeWithTag(TAG_HUB_PREVIEW_FRAME).assertDoesNotExist()
        compose.onNodeWithText("Try again").performClick()
        assertEquals(1, retried)
    }
}
