package com.shikkhokplus.app.navigation

import androidx.compose.material3.Text
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.session.WORKSPACE_HEADER
import com.shikkhokplus.app.feature.hublisting.FeedbackAnswer
import com.shikkhokplus.app.feature.hublisting.ui.hubFeedbackTag
import com.shikkhokplus.app.feature.inbox.InboxTarget
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

/**
 * The demand question, driven through the real route from its inbox target.
 *
 * **A previous unit shipped an action the route never passed**, and the
 * view model's own test could not see it. So this opens the screen the
 * way the inbox does, taps a reply, and asserts that the answer reached
 * the server for the item's owner and day.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class HubFeedbackRouteTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `tapping a reply sends it for the inbox item's owner and day`() {
        val sent = Collections.synchronizedList(mutableListOf<Pair<String?, String>>())
        val engine =
            MockEngine { request ->
                sent += request.headers[WORKSPACE_HEADER] to (request.body as TextContent).text
                respond("", HttpStatusCode.NoContent)
            }
        val client = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())
        lateinit var nav: NavHostController

        compose.setContent {
            ShikkhokTheme {
                nav = rememberNavController()
                NavHost(nav, startDestination = HOME) {
                    composable(HOME) { Text("home") }
                    hubRoutes(client, nav)
                }
            }
        }
        compose.runOnIdle { nav.navigate(InboxTarget.HubFeedback("centre-1", 90).route()) }

        compose.onNodeWithText("Did the hub bring you a student?").assertExists()
        compose.onNodeWithText("90 days after you first published").assertExists()
        compose.onNodeWithTag(hubFeedbackTag(FeedbackAnswer.NOT_YET)).performClick()

        compose.waitUntil(timeoutMillis = 5_000) { sent.isNotEmpty() }
        assertEquals(listOf("centre-1" to """{"day":90,"answer":"not_yet"}"""), sent.toList())
        // The server's acceptance is what the screen then reports.
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText(THANKS).fetchSemanticsNodes().isNotEmpty()
        }
    }

    private companion object {
        /** A plain start screen, so the feedback route is navigated to. */
        const val HOME = "home"

        /** What the screen says once the server accepted an answer. */
        const val THANKS = "Thank you. You can change your answer here at any time."
    }
}
