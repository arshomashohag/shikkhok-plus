package com.shikkhokplus.app.feature.hublisting

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The languages a hub page is served in. */
internal val HUB_LOCALES: List<String> = listOf("bn", "en")

/**
 * Read a locale as one a hub page is served in.
 *
 * @param locale A language tag, or null
 * @return `bn` for Bangla, `en` for anything else
 */
internal fun hubLocale(locale: String?): String = if (locale == "bn") "bn" else "en"

/**
 * Where an owner's published page lives on the public site.
 *
 * @param site The site's origin, `BuildConfig.SITE_URL`
 * @param locale `bn` or `en`
 * @param slug The owner's slug, as the server holds it
 * @return The page's URL
 */
fun publicPageUrl(site: String, locale: String, slug: String): String =
    "${site.trimEnd('/')}/hub/${hubLocale(locale)}/t/${java.net.URLEncoder.encode(slug, "UTF-8")}"

/** What the preview screen needs from the network. */
fun interface HubPreviewApi {
    /**
     * Read the owner's page as it would read once published, drafts included.
     *
     * @param locale `bn` or `en`
     * @return The page's HTML as the server sent it, a refusal, or a transport failure
     */
    suspend fun preview(locale: String): AuthResult<String>
}

/** What the preview screen renders. */
sealed interface HubPreviewUiState {
    /** Waiting for the page. */
    data object Loading : HubPreviewUiState

    /**
     * The server's page, shown as sent in a WebView that runs no script.
     *
     * @property html The page
     */
    data class Ready(val html: String) : HubPreviewUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Whether to offer a retry
     */
    data class Error(val messageKey: String, val retryable: Boolean) : HubPreviewUiState
}

/**
 * The preview screen.
 *
 * @property locale The language the page is read in
 * @property body What is shown
 */
data class HubPreviewState(
    val locale: String,
    val body: HubPreviewUiState = HubPreviewUiState.Loading,
)

/**
 * Holds "Preview as public": the server's page for the owner, in either
 * language. It decides nothing about the page; it only reads it.
 *
 * @property api The network
 * @param locale The language to start in
 */
class HubPreviewViewModel(
    private val api: HubPreviewApi,
    locale: String,
) : ViewModel() {

    private val _state = MutableStateFlow(HubPreviewState(hubLocale(locale)))

    /** What the screen renders. */
    val state: StateFlow<HubPreviewState> = _state.asStateFlow()

    private var reading: Job? = null

    /** Read the page, unless it is showing already (rotation, coming back). */
    fun load() {
        if (_state.value.body is HubPreviewUiState.Ready) return
        read()
    }

    /** Read the page again after a failure. */
    fun retry() {
        if (_state.value.body !is HubPreviewUiState.Error) return
        read()
    }

    /**
     * Show the page in another language.
     *
     * @param locale `bn` or `en`
     */
    fun switchLocale(locale: String) {
        val next = hubLocale(locale)
        if (next == _state.value.locale) return
        _state.update { it.copy(locale = next) }
        read()
    }

    private fun read() {
        val locale = _state.value.locale
        reading?.cancel()
        _state.update { it.copy(body = HubPreviewUiState.Loading) }
        reading =
            viewModelScope.launch {
                val body =
                    when (val result = api.preview(locale)) {
                        is AuthResult.Ok -> HubPreviewUiState.Ready(result.value)
                        else ->
                            result.hubFailure()?.let { HubPreviewUiState.Error(it.messageKey, it.canRetry) }
                                ?: HubPreviewUiState.Error("error.unexpected", retryable = false)
                    }
                _state.update { if (it.locale == locale) it.copy(body = body) else it }
            }
    }
}
