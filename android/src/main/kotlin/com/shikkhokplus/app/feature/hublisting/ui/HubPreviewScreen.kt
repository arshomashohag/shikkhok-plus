package com.shikkhokplus.app.feature.hublisting.ui

import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.viewinterop.AndroidView
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hublisting.HUB_LOCALES
import com.shikkhokplus.app.feature.hublisting.HubPreviewState
import com.shikkhokplus.app.feature.hublisting.HubPreviewUiState

/** The WebView the server's page is shown in. */
const val TAG_HUB_PREVIEW_FRAME: String = "hub_preview_frame"

/**
 * The base URL the preview is loaded on: `about:blank`, an origin of no
 * site and no file, so the page can reach nothing on the phone and the
 * stylesheet it names absolutely on the public site still loads [R11].
 */
const val PREVIEW_BASE_URL: String = "about:blank"

/** Each locale's name, as the language setting writes it. */
private val LANGUAGE_NAME: Map<String, Int> =
    mapOf("bn" to R.string.settings_language_bangla, "en" to R.string.settings_language_english)

/**
 * The language chip for a locale.
 *
 * @param locale `bn` or `en`
 * @return Its test tag
 */
fun hubPreviewLocaleTag(locale: String): String = "hub_preview_locale_$locale"

/**
 * What the preview screen's controls call.
 *
 * @property onLocale Shows the page in another language
 * @property onRetry Reads the page again after a failure
 * @property onBack Leaves the screen
 */
data class HubPreviewActions(
    val onLocale: (String) -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * Lock a WebView down to showing one server page and nothing else.
 *
 * **No script**: the page is the server's HTML and carries none, and a
 * WebView with JavaScript off cannot be made to run any. **No file or
 * content access**: nothing on the phone is reachable from the page.
 * **No navigation**: a link tapped in the preview is ignored rather than
 * loaded in the WebView or opened in the browser -- the preview is a look
 * at the page, and its links lead to pages that are not public yet. No
 * second window opens either.
 *
 * @param view The WebView
 */
fun configurePreviewWebView(view: WebView) {
    view.settings.apply {
        javaScriptEnabled = false
        javaScriptCanOpenWindowsAutomatically = false
        allowFileAccess = false
        allowContentAccess = false
        domStorageEnabled = false
        setSupportMultipleWindows(false)
        setGeolocationEnabled(false)
    }
    view.webViewClient = PreviewWebViewClient
}

/** Refuses every navigation away from the loaded page. */
private object PreviewWebViewClient : WebViewClient() {
    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean = true
}

/**
 * Show the server's page in a WebView set up by [configurePreviewWebView].
 *
 * @param view The WebView
 * @param html The page, as the server sent it
 */
fun loadPreview(view: WebView, html: String) {
    view.loadDataWithBaseURL(PREVIEW_BASE_URL, html, "text/html", "UTF-8", null)
}

/**
 * "Preview as public": the owner's page as it would read once published,
 * drafts included, in either language. The page is the server's; the
 * screen only shows it, in a WebView that runs nothing.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun HubPreviewScreen(
    state: HubPreviewState,
    actions: HubPreviewActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.hub_preview_as_public),
        modifier = modifier,
        scrollable = false,
        onBack = actions.onBack,
        pinned = {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
                HUB_LOCALES.forEach { locale ->
                    FilterChip(
                        selected = locale == state.locale,
                        onClick = { actions.onLocale(locale) },
                        label = { Text(stringResource(LANGUAGE_NAME.getValue(locale))) },
                        modifier = Modifier.testTag(hubPreviewLocaleTag(locale)),
                    )
                }
            }
        },
    ) {
        when (val body = state.body) {
            HubPreviewUiState.Loading -> SkeletonList(rows = 4)
            is HubPreviewUiState.Error ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = null,
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) actions.onRetry else null,
                )
            is HubPreviewUiState.Ready ->
                AndroidView(
                    factory = { context -> WebView(context).also(::configurePreviewWebView) },
                    // Loaded again only when the page itself changed, so a
                    // recomposition does not reset the reader's scroll.
                    update = { view ->
                        if (view.tag != body.html) {
                            view.tag = body.html
                            loadPreview(view, body.html)
                        }
                    },
                    modifier = Modifier.fillMaxSize().testTag(TAG_HUB_PREVIEW_FRAME),
                )
        }
    }
}
