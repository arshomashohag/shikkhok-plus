package com.shikkhokplus.app.feature.hublisting

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/** The owner's "Preview as public": what it reads and what it shows. */
@OptIn(ExperimentalCoroutinesApi::class)
class HubPreviewViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    /** Answers each read from [answers] in turn, recording the locale asked for. */
    private class FakePreviewApi(vararg answers: AuthResult<String>) : HubPreviewApi {
        private val pending = ArrayDeque(answers.toList())
        val asked = mutableListOf<String>()

        override suspend fun preview(locale: String): AuthResult<String> {
            asked += locale
            return pending.removeFirstOrNull() ?: AuthResult.Ok("<p>$locale</p>")
        }
    }

    private fun refusal(key: String, retryable: Boolean) =
        AuthResult.Refused(ErrorEnvelope(ErrorBody("X", retryable, key)))

    @Test
    fun the_servers_page_is_shown_as_sent_in_the_locale_asked_for() = runTest(dispatcher) {
        val api = FakePreviewApi(AuthResult.Ok("<html>bn page</html>"))
        val vm = HubPreviewViewModel(api, "bn")
        assertIs<HubPreviewUiState.Loading>(vm.state.value.body)

        vm.load()
        advanceUntilIdle()

        assertEquals(listOf("bn"), api.asked)
        assertEquals("bn", vm.state.value.locale)
        assertEquals("<html>bn page</html>", assertIs<HubPreviewUiState.Ready>(vm.state.value.body).html)

        // Coming back to the screen does not read it again.
        vm.load()
        advanceUntilIdle()
        assertEquals(listOf("bn"), api.asked)
    }

    @Test
    fun switching_the_language_reads_the_page_in_it() = runTest(dispatcher) {
        val api = FakePreviewApi()
        val vm = HubPreviewViewModel(api, "en")
        vm.load()
        advanceUntilIdle()

        vm.switchLocale("bn")
        advanceUntilIdle()
        vm.switchLocale("bn")
        advanceUntilIdle()

        assertEquals(listOf("en", "bn"), api.asked)
        assertEquals("bn", vm.state.value.locale)
        assertEquals("<p>bn</p>", assertIs<HubPreviewUiState.Ready>(vm.state.value.body).html)
    }

    @Test
    fun a_refusal_shows_the_servers_message_and_retry_reads_again() = runTest(dispatcher) {
        val api = FakePreviewApi(refusal("error.network.unreachable", retryable = true))
        val vm = HubPreviewViewModel(api, "en")
        vm.load()
        advanceUntilIdle()

        val error = assertIs<HubPreviewUiState.Error>(vm.state.value.body)
        assertEquals("error.network.unreachable", error.messageKey)
        assertEquals(true, error.retryable)

        vm.retry()
        advanceUntilIdle()
        assertEquals(listOf("en", "en"), api.asked)
        assertIs<HubPreviewUiState.Ready>(vm.state.value.body)
    }

    @Test
    fun a_transport_failure_offers_retry_and_an_unknown_locale_reads_english() = runTest(dispatcher) {
        val api = FakePreviewApi(AuthResult.TransportFailure)
        val vm = HubPreviewViewModel(api, "fr")
        vm.load()
        advanceUntilIdle()

        assertEquals(listOf("en"), api.asked)
        assertEquals(HubPreviewUiState.Error(HUB_OFFLINE_KEY, retryable = true), vm.state.value.body)
    }

    @Test
    fun the_public_page_lives_on_the_site_under_the_locale_and_slug() {
        val site = "https://site.example"
        assertEquals("$site/hub/bn/t/rahima", publicPageUrl("$site/", "bn", "rahima"))
        assertEquals("$site/hub/en/t/rahim-sir", publicPageUrl(site, "en", "rahim-sir"))
    }
}
