package com.shikkhokplus.app.navigation

import androidx.compose.material3.Text
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.feature.hubreviews.ui.reviewStarTag
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.Collections
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The inbox, driven through the real routes: an item is shown in words,
 * and tapping it opens the screen it is about.
 *
 * **A previous unit shipped an action the route never passed**, and the
 * mapper's own test could not see it. So this taps the row the reader
 * sees and asserts which destination opened and what it read.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class InboxRouteTest {

    @get:Rule
    val compose = createComposeRule()

    private val json = headersOf("Content-Type", ContentType.Application.Json.toString())

    /** Every request the screens made beyond reading the inbox, as `METHOD path`. */
    private val reads = Collections.synchronizedList(mutableListOf<String>())

    private fun host(): NavHostController {
        val engine =
            MockEngine { request ->
                val path = request.url.encodedPath
                if (path != "/v1/me/notifications") reads += "${request.method.value} $path"
                when {
                    path == "/v1/me/notifications" -> respond(INBOX, HttpStatusCode.OK, json)
                    request.method == HttpMethod.Post -> respond("", HttpStatusCode.NoContent)
                    path == "/v1/hub/batches/$BATCH/my-review" -> respond(MINE, HttpStatusCode.OK, json)
                    path == "/v1/hub/reviews" -> respond(OWNER, HttpStatusCode.OK, json)
                    path == "/v1/hub/enquiries/$ENQUIRY" -> respond(REQUEST, HttpStatusCode.OK, json)
                    path == "/v1/me/hub/enquiries" -> respond("[]", HttpStatusCode.OK, json)
                    else -> respond("", HttpStatusCode.NotFound)
                }
            }
        val client = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())
        lateinit var nav: NavHostController
        compose.setContent {
            ShikkhokTheme {
                nav = rememberNavController()
                NavHost(nav, startDestination = HOME) {
                    composable(HOME) { Text(HOME) }
                    studentRoutes(client, nav) {}
                    hubRoutes(client, nav)
                }
            }
        }
        compose.runOnIdle { nav.navigate(Destination.Inbox.route) }
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText(OUTCOME_TITLE).fetchSemanticsNodes().isNotEmpty()
        }
        // Let the list's fade-in finish, so a tap lands on the row and not
        // on the loading placeholder fading out above it.
        compose.waitForIdle()
        return nav
    }

    @Test
    fun `both review kinds are shown in words, never as their raw preview`() {
        host()

        compose.onNodeWithText("Your review was not published. Open it to see why.").assertExists()
        compose.onNodeWithText("New reviews · Physics 9").assertExists()
        compose.onNodeWithText("New reviews published: 2").assertExists()
        assertTrue(compose.onAllNodesWithText("rejected").fetchSemanticsNodes().isEmpty())
    }

    @Test
    fun `a review outcome opens its review in the editor`() {
        val nav = host()

        compose.onNodeWithText(OUTCOME_TITLE).performClick()

        // A semantics query, not the request list, so the wait lets the main
        // looper run the navigation the tap posted.
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithTag(reviewStarTag(1)).fetchSemanticsNodes().isNotEmpty()
        }
        compose.runOnIdle {
            assertTrue("GET /v1/hub/batches/$BATCH/my-review" in reads, "$reads")
            assertEquals(Destination.HubReviewEditor.route, nav.currentDestination?.route)
            assertEquals(BATCH, nav.currentBackStackEntry?.arguments?.getString(Destination.HubReviewEditor.ARG_BATCH))
        }
    }

    @Test
    fun `new reviews open the owner's Reviews screen`() {
        val nav = host()

        compose.onNodeWithText("New reviews · Physics 9").performClick()

        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText("No published reviews yet.").fetchSemanticsNodes().isNotEmpty()
        }
        compose.runOnIdle {
            assertTrue("GET /v1/hub/reviews" in reads, "$reads")
            assertEquals(Destination.HubOwnerReviews.route, nav.currentDestination?.route)
        }
    }

    @Test
    fun `both join-request kinds are shown in words, never as their raw preview`() {
        host()

        compose.onNodeWithText(RECEIVED_TITLE).assertExists()
        compose.onNodeWithText("Open it to see the request.").assertExists()
        compose.onNodeWithText("Your join request · Physics 9").assertExists()
        compose.onNodeWithText("Please call the teacher.").assertExists()
        assertTrue(compose.onAllNodesWithText("call_us").fetchSemanticsNodes().isEmpty())
    }

    @Test
    fun `a join request received opens the request in the owner's inbox`() {
        val nav = host()

        compose.onNodeWithText(RECEIVED_TITLE).performClick()

        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText("Wants Physics").fetchSemanticsNodes().isNotEmpty()
        }
        compose.runOnIdle {
            assertTrue("GET /v1/hub/enquiries/$ENQUIRY" in reads, "$reads")
            assertEquals(Destination.HubOwnerEnquiry.route, nav.currentDestination?.route)
            assertEquals(ENQUIRY, nav.currentBackStackEntry?.arguments?.getString(Destination.HubOwnerEnquiry.ARG_ID))
        }
    }

    @Test
    fun `a join request answered opens my requests`() {
        val nav = host()

        compose.onNodeWithText("Your join request · Physics 9").performClick()

        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText("You have no join requests.").fetchSemanticsNodes().isNotEmpty()
        }
        compose.runOnIdle {
            assertTrue("GET /v1/me/hub/enquiries" in reads, "$reads")
            assertEquals(Destination.HubMyEnquiries.route, nav.currentDestination?.route)
        }
    }

    private companion object {
        const val HOME = "home"
        const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"
        const val OWNER_ID = "6f1c2b0e-3a4d-4e5f-8a9b-0c1d2e3f4a5b"
        const val OUTCOME_TITLE = "Your review · Physics 9"
        const val RECEIVED_TITLE = "New join request · Physics 9"
        const val ENQUIRY = "e1111111-1111-4111-8111-111111111111"

        const val INBOX =
            """{"unread":4,"items":[""" +
                """{"notification_id":"n-1","kind":"hub_review_outcome","batch_name":"Physics 9",""" +
                """"created_at":"2026-11-19T06:00:00Z","read":false,"source_id":"$BATCH","preview":"rejected"},""" +
                """{"notification_id":"n-2","kind":"hub_reviews_published","batch_name":"Physics 9",""" +
                """"created_at":"2026-11-19T05:00:00Z","read":false,"source_id":"$OWNER_ID","preview":"2"},""" +
                """{"notification_id":"n-3","kind":"hub_enquiry_received","batch_name":"Physics 9",""" +
                """"created_at":"2026-11-19T04:00:00Z","read":false,"source_id":"$ENQUIRY","preview":null},""" +
                """{"notification_id":"n-4","kind":"hub_enquiry_answered","batch_name":"Physics 9",""" +
                """"created_at":"2026-11-19T03:00:00Z","read":false,"source_id":"$ENQUIRY","preview":"call_us"}]}"""

        const val REQUEST =
            """{"id":"$ENQUIRY","batch_id":null,"batch_title":"Physics 9","student_name":"Nadia",""" +
                """"class_level":"class_8","message":"Wants Physics","status":"open","outcome":null,""" +
                """"received_at":"2026-11-19T04:00:00Z","guardian_phone":null,"guardian_email":null,""" +
                """"outcomes_allowed":["not_now"]}"""

        const val MINE =
            """{"standing":"eligible","waiting_on":null,"eligible_from":null,"can_write":true,""" +
                """"edit_until":"2026-12-19","review":{"rating":2,"body":"Call me","status":"rejected",""" +
                """"rejection_code":"personal_info","tenure":"lt_6m","published_month":null,"reply_body":null}}"""

        const val OWNER = """{"batches":[],"reviews":[]}"""
    }
}
