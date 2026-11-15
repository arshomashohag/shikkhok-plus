package com.shikkhokplus.app.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.designsystem.TAG_SCAFFOLD_BACK
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.HttpProfileRepository
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.session.SessionViewModel
import com.shikkhokplus.app.core.session.ui.LensPickerScreen
import com.shikkhokplus.app.core.session.ui.TAG_LENS_PICKER
import com.shikkhokplus.app.core.ui.AvailabilityState
import com.shikkhokplus.app.feature.account.ChooseUsernameUiState
import com.shikkhokplus.app.feature.account.ui.ChooseUsernameGate
import com.shikkhokplus.app.feature.account.ui.TAG_CHOOSE_USERNAME_GATE
import com.shikkhokplus.app.feature.account.ui.TAG_CHOOSE_USERNAME_SIGN_OUT
import com.shikkhokplus.app.feature.auth.ui.TAG_CODE_BACK
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Which screen the signed-in root shows when the account must choose a
 * username [FR5.2; NFR3.12-3.14, NFR8.5, NFR8.6], written first.
 *
 * **The app's own decision, under a harness.** `AppRoot` builds an
 * encrypted token store and a Keystore-backed queue that Robolectric
 * cannot construct, so this composes the parts that decide the screen --
 * the real [SessionViewModel] over the real [HttpProfileRepository] and
 * [ApiClient] with a [MockEngine] answering `GET /v1/me`, the shared
 * [rootRouteFor] that `AppRoot` routes on, and the shared
 * [FailedRecheckEffect] -- and stands simple tagged boxes in for the
 * home and the sign-in screen.
 *
 * Every composed frame records which slot it drew, so "the gate is the
 * first frame after the loader" is asserted over the whole sequence and
 * not only over the final screen.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class UsernameGateRoutingTest {

    @get:Rule
    val compose = createComposeRule()

    private val frames = CopyOnWriteArrayList<String>()
    private val reads = AtomicInteger(0)
    private val tokens = TokenStore.InMemory().apply { save("access", "refresh") }

    /** Answer the n-th `GET /v1/me` with the n-th body, the last one thereafter. */
    private fun model(vararg answers: Pair<HttpStatusCode, String>): SessionViewModel {
        val engine =
            MockEngine { request ->
                assertEquals("/v1/me", request.url.encodedPath)
                val n = reads.getAndIncrement()
                val (status, body) = answers[minOf(n, answers.lastIndex)]
                respond(body, status, headersOf("Content-Type", "application/json"))
            }
        return SessionViewModel(HttpProfileRepository(ApiClient.build("https://staging.example", engine, tokens)))
    }

    /** The signed-in root, routed as `AppRoot` routes it. */
    @Composable
    private fun Root(session: SessionViewModel, onSignOut: () -> Unit) {
        LaunchedEffect(Unit) { session.resolve() }
        val state by session.state.collectAsState()
        FailedRecheckEffect(state, session::recheck)
        when (val route = rootRouteFor(state)) {
            RootRoute.Loader -> Slot(LOADER)
            RootRoute.Gate -> {
                SideEffect { frames += GATE }
                ChooseUsernameGate(
                    state = ChooseUsernameUiState.Editing(),
                    availability = AvailabilityState.Idle,
                    onEdited = {},
                    onSubmit = {},
                    onRetry = {},
                    onSignOut = onSignOut,
                )
            }
            is RootRoute.Picker -> {
                SideEffect { frames += PICKER }
                LensPickerScreen(options = route.options, onChoose = session::choose)
            }
            is RootRoute.Graph -> Slot(HOME)
        }
    }

    @Composable
    private fun Slot(name: String) {
        SideEffect { frames += name }
        Box(Modifier.testTag(name))
    }

    private fun show(session: SessionViewModel) {
        val signedIn = mutableStateOf(true)
        compose.setContent {
            ShikkhokTheme {
                if (signedIn.value) {
                    Root(session) {
                        // The app's one endSession, as far as the gate can see it.
                        tokens.clear()
                        signedIn.value = false
                    }
                } else {
                    Slot(SIGN_IN)
                }
            }
        }
    }

    private fun waitFor(tag: String) =
        compose.waitUntil(TIMEOUT_MS) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }

    private fun present(tag: String): Boolean =
        compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()

    @Test
    fun `first composed frame after Resolving is the gate when the read says true`() {
        show(model(HttpStatusCode.OK to REQUIRED_ONE_LENS))

        waitFor(TAG_CHOOSE_USERNAME_GATE)

        val shown = frames.filter { it != LOADER }
        assertEquals(GATE, shown.first(), "$frames")
        assertTrue(HOME !in frames && PICKER !in frames, "a screen preceded the gate: $frames")
        assertTrue(!present(HOME) && !present(TAG_LENS_PICKER))
    }

    @Test
    fun `the gate has no back arrow`() {
        show(model(HttpStatusCode.OK to REQUIRED_ONE_LENS))

        waitFor(TAG_CHOOSE_USERNAME_GATE)

        assertTrue(!present(TAG_SCAFFOLD_BACK) && !present(TAG_CODE_BACK))
    }

    @Test
    fun `after usernameChosen the home shows`() {
        val session = model(HttpStatusCode.OK to REQUIRED_ONE_LENS)
        show(session)
        waitFor(TAG_CHOOSE_USERNAME_GATE)

        compose.runOnIdle { session.usernameChosen() }

        waitFor(HOME)
        assertTrue(!present(TAG_CHOOSE_USERNAME_GATE))
    }

    @Test
    fun `after usernameChosen the lens picker shows for several lenses`() {
        val session = model(HttpStatusCode.OK to REQUIRED_TWO_LENSES)
        show(session)
        waitFor(TAG_CHOOSE_USERNAME_GATE)

        compose.runOnIdle { session.usernameChosen() }

        waitFor(TAG_LENS_PICKER)
        assertTrue(!present(TAG_CHOOSE_USERNAME_GATE) && !present(HOME))
    }

    @Test
    fun `Sign out from the gate reaches sign-in with the token store cleared`() {
        show(model(HttpStatusCode.OK to REQUIRED_ONE_LENS))
        waitFor(TAG_CHOOSE_USERNAME_GATE)

        compose.onNodeWithTag(TAG_CHOOSE_USERNAME_SIGN_OUT).performClick()

        waitFor(SIGN_IN)
        assertNull(tokens.refreshToken())
        assertNull(tokens.accessToken())
    }

    @Test
    fun `failed read then foreground re-check showing true replaces the lens-free graph with the gate`() {
        // Cold start fails, the re-check on coming to the front fails
        // too, and the one after the 30-second wait finally reads true.
        show(
            model(
                HttpStatusCode.ServiceUnavailable to UNAVAILABLE,
                HttpStatusCode.ServiceUnavailable to UNAVAILABLE,
                HttpStatusCode.OK to REQUIRED_ONE_LENS,
            ),
        )
        compose.mainClock.autoAdvance = false
        settleUntil { reads.get() >= 2 && present(HOME) }
        assertTrue(!present(TAG_CHOOSE_USERNAME_GATE), "the gate showed before any read said true")

        // Well inside the interval: nothing more is asked.
        compose.mainClock.advanceTimeBy(HALF_INTERVAL_MS)
        settleUntil { true }
        assertEquals(2, reads.get(), "a re-check ran before the interval elapsed")

        compose.mainClock.advanceTimeBy(RECHECK_INTERVAL_MS)
        settleUntil { present(TAG_CHOOSE_USERNAME_GATE) }

        assertEquals(3, reads.get())
        assertTrue(!present(HOME))
    }

    @Test
    fun `the re-check cadence is thirty seconds`() {
        assertEquals(30_000L, RECHECK_INTERVAL_MS)
    }

    /** Produce frames one at a time until [done], under the paused clock. */
    private fun settleUntil(done: () -> Boolean) {
        compose.waitUntil(TIMEOUT_MS) {
            compose.mainClock.advanceTimeByFrame()
            done()
        }
    }

    private companion object {
        const val LOADER = "test_loader"
        const val HOME = "test_home"
        const val SIGN_IN = "test_sign_in"
        const val GATE = "gate"
        const val PICKER = "picker"
        const val TIMEOUT_MS = 5_000L
        const val HALF_INTERVAL_MS = 15_000L

        const val REQUIRED_ONE_LENS =
            """{"lenses":[{"kind":"teacher","count":1}],"username":null,"username_required":true}"""
        const val REQUIRED_TWO_LENSES =
            """{"lenses":[{"kind":"teacher","count":1},{"kind":"guardian","count":1}],""" +
                """"username":null,"username_required":true}"""
        const val UNAVAILABLE =
            """{"error":{"code":"UNAVAILABLE","retryable":true,"message_key":"error.temporarily_unavailable"}}"""
    }
}
