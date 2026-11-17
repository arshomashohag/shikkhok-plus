package com.shikkhokplus.app.navigation

import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.feature.hublisting.report.ReportLink
import com.shikkhokplus.app.feature.hublisting.report.ReportReason
import com.shikkhokplus.app.feature.hublisting.report.ui.TAG_HUB_REPORT_NOTE
import com.shikkhokplus.app.feature.hublisting.report.ui.hubReportReasonTag
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.Collections
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The report screen, driven through the real route from an App Link.
 *
 * **A previous unit shipped an action the route never passed**, and the
 * view model's own test could not see it. So this opens the screen the
 * way `MainActivity` does -- through [HubReportLinkEffect] with the link
 * the intent carried -- picks a reason, writes a note, taps Send, and
 * asserts what reached the server.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class HubReportRouteTest {

    @get:Rule
    val compose = createComposeRule()

    private val sent = Collections.synchronizedList(mutableListOf<Pair<String, String>>())

    private val client =
        ApiClient.build(
            "https://staging.example",
            MockEngine { request ->
                sent += request.url.encodedPath to (request.body as TextContent).text
                respond("", HttpStatusCode.Accepted)
            },
            TokenStore.InMemory(),
        )

    /** The app's shape in small: sign-in when signed out, home when in, plus the hub routes. */
    private fun host(link: () -> ReportLink?, signedIn: () -> Boolean, onOpened: () -> Unit) {
        compose.setContent {
            ShikkhokTheme {
                // Keyed on the session, as MainActivity's graph is.
                key(signedIn()) {
                    val nav: NavHostController = rememberNavController()
                    NavHost(nav, startDestination = if (signedIn()) HOME else SIGN_IN) {
                        composable(SIGN_IN) { Text(SIGN_IN) }
                        composable(HOME) { Text(HOME) }
                        hubRoutes(client, nav)
                    }
                    HubReportLinkEffect(nav, signedIn(), link(), onOpened)
                }
            }
        }
    }

    @Test
    fun `a report link opens the form and sends the chosen reason and note`() {
        var pending: ReportLink? by mutableStateOf(ReportLink("batch_listing", BATCH))
        host({ pending }, { true }) { pending = null }

        compose.onNodeWithText("A batch's public page").assertExists()
        compose.onNodeWithTag(hubReportReasonTag(ReportReason.FAKE)).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_HUB_REPORT_NOTE).performScrollTo().performTextInput("Same photo as another centre")
        compose.onNodeWithText("Send report").performScrollTo().performClick()

        compose.waitUntil(timeoutMillis = 5_000) { sent.isNotEmpty() }
        assertEquals(
            listOf(
                "/v1/hub/reports" to
                    """{"target_kind":"batch_listing","target_id":"$BATCH","reason":"fake",""" +
                    """"note":"Same photo as another centre"}""",
            ),
            sent.toList(),
        )
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText(THANKS, substring = true).fetchSemanticsNodes().isNotEmpty()
        }
        assertNull(pending, "the link was consumed, so it cannot open twice")
    }

    @Test
    fun `a signed-out reader is sent through sign-in and back to the report`() {
        var signedIn by mutableStateOf(false)
        var pending: ReportLink? by mutableStateOf(ReportLink("owner_listing", OWNER))
        host({ pending }, { signedIn }) { pending = null }

        compose.onNodeWithText(SIGN_IN).assertExists()
        compose.onAllNodesWithText("Report this page").fetchSemanticsNodes().let { assertTrue(it.isEmpty()) }
        assertEquals(ReportLink("owner_listing", OWNER), pending, "kept until there is someone to report as")

        compose.runOnIdle { signedIn = true }

        compose.onNodeWithText("A teacher's or coaching centre's public page").assertExists()
        compose.runOnIdle { assertNull(pending) }
    }

    @Test
    fun `a malformed link says so and sends nothing`() {
        var pending: ReportLink? by mutableStateOf(ReportLink("media", "sumi-apa"))
        host({ pending }, { true }) { pending = null }

        compose.onNodeWithText("This link isn't valid.").assertExists()
        compose.onAllNodesWithText("Send report").fetchSemanticsNodes().let { assertTrue(it.isEmpty()) }
        compose.runOnIdle { assertTrue(sent.isEmpty()) }
    }

    private companion object {
        const val SIGN_IN = "sign-in"
        const val HOME = "home"
        const val OWNER = "6f1c2b0e-3a4d-4e5f-8a9b-0c1d2e3f4a5b"
        const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"

        /** What the screen says once the server accepted the report. */
        const val THANKS = "Thank you. We will look at this page."
    }
}
