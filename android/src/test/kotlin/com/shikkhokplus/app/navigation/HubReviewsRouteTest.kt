package com.shikkhokplus.app.navigation

import androidx.compose.material3.Text
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.designsystem.TAG_ERROR_RETRY
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_REVIEWS
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_REVIEWS
import com.shikkhokplus.app.feature.hubreviews.ui.TAG_REPLY_DELETE_CONFIRM
import com.shikkhokplus.app.feature.hubreviews.ui.TAG_REVIEW_BODY
import com.shikkhokplus.app.feature.hubreviews.ui.TAG_REVIEW_DELETE
import com.shikkhokplus.app.feature.hubreviews.ui.TAG_REVIEW_DELETE_CONFIRM
import com.shikkhokplus.app.feature.hubreviews.ui.TAG_REVIEW_SAVE
import com.shikkhokplus.app.feature.hubreviews.ui.hubReviewsRowTag
import com.shikkhokplus.app.feature.hubreviews.ui.replyDeleteTag
import com.shikkhokplus.app.feature.hubreviews.ui.replyFieldTag
import com.shikkhokplus.app.feature.hubreviews.ui.replyReportTag
import com.shikkhokplus.app.feature.hubreviews.ui.replySendTag
import com.shikkhokplus.app.feature.hubreviews.ui.reviewStarTag
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.Collections
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Guardian reviews and the owner's Reviews screen, driven through the
 * real routes with the real HTTP client.
 *
 * **A previous unit shipped an action the route never passed**, and the
 * view model's own test could not see it. So each action here starts
 * where a person starts -- the guardian home's Reviews row, the listing
 * editor's Reviews row -- and is proven by what reached the server or
 * which destination opened.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class HubReviewsRouteTest {

    @get:Rule
    val compose = createComposeRule()

    private val json = headersOf("Content-Type", ContentType.Application.Json.toString())

    /** Every write, as `METHOD path body`. */
    private val writes = Collections.synchronizedList(mutableListOf<String>())

    private fun MockRequestHandleScope.ok(body: String): HttpResponseData = respond(body, HttpStatusCode.OK, json)

    private fun record(request: HttpRequestData) {
        val body = (request.body as? TextContent)?.text.orEmpty()
        writes += "${request.method.value} ${request.url.encodedPath} $body".trim()
    }

    private fun host(
        start: String,
        handle: MockRequestHandleScope.(HttpRequestData) -> HttpResponseData,
    ): NavHostController {
        val client = ApiClient.build("https://staging.example", MockEngine { handle(it) }, TokenStore.InMemory())
        lateinit var nav: NavHostController
        compose.setContent {
            ShikkhokTheme {
                nav = rememberNavController()
                NavHost(nav, startDestination = HOME) {
                    composable(HOME) { Text(HOME) }
                    guardianHomeRoute(client, nav)
                    hubRoutes(client, nav)
                }
            }
        }
        compose.runOnIdle { nav.navigate(start) }
        return nav
    }

    private fun waitForTag(tag: String) =
        compose.waitUntil(timeoutMillis = 5_000) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }

    private fun waitForText(text: String) =
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText(text, substring = true).fetchSemanticsNodes().isNotEmpty()
        }

    @Test
    fun `the guardian home row opens the list, then the editor, and submit, edit and delete reach the server`() {
        var review: String = ELIGIBLE
        val nav =
            host(Destination.GuardianHome.route) { request ->
                val path = request.url.encodedPath
                when {
                    path == "/v1/guardian/home" -> ok(GUARDIAN_HOME)
                    path == "/v1/me/notifications" -> ok("""{"items":[],"unread":0}""")
                    path == "/v1/hub/reviewable" -> ok(REVIEWABLE)
                    path == MY_REVIEW && request.method == HttpMethod.Get -> ok(review)
                    path == MY_REVIEW && request.method == HttpMethod.Put -> {
                        record(request)
                        review = PENDING
                        ok(review)
                    }
                    path == MY_REVIEW && request.method == HttpMethod.Delete -> {
                        record(request)
                        review = ELIGIBLE
                        respond("", HttpStatusCode.NoContent)
                    }
                    else -> respond("", HttpStatusCode.NotFound)
                }
            }

        waitForTag(TAG_GUARDIAN_REVIEWS)
        compose.onNodeWithTag(TAG_GUARDIAN_REVIEWS).performScrollTo().performClick()
        waitForTag(hubReviewsRowTag(BATCH))
        compose.runOnIdle { assertEquals(Destination.HubMyReviews.route, nav.currentDestination?.route) }
        compose.onNodeWithText("Rahima").assertExists()
        compose.onNodeWithTag(hubReviewsRowTag(BATCH)).performClick()

        waitForTag(reviewStarTag(5))
        compose.runOnIdle { assertEquals(Destination.HubReviewEditor.route, nav.currentDestination?.route) }
        compose.onNodeWithText("Physics 9").assertExists()
        compose.onNodeWithTag(reviewStarTag(5)).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_REVIEW_BODY).performScrollTo().performTextInput("Clear teaching")
        compose.onNodeWithTag(TAG_REVIEW_SAVE).performScrollTo().performClick()

        compose.waitUntil(timeoutMillis = 5_000) { writes.isNotEmpty() }
        assertEquals("PUT $MY_REVIEW {\"rating\":5,\"body\":\"Clear teaching\"}", writes[0])
        waitForText("Awaiting review")
        compose.onNodeWithText("Save changes").assertExists()

        // Editing sends the changed rating and words.
        compose.onNodeWithTag(reviewStarTag(4)).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_REVIEW_BODY).performScrollTo().performTextClearance()
        compose.onNodeWithTag(TAG_REVIEW_SAVE).performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 5_000) { writes.size == 2 }
        assertEquals("PUT $MY_REVIEW {\"rating\":4}", writes[1])

        // Delete only from its confirmation.
        compose.onNodeWithTag(TAG_REVIEW_DELETE).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_REVIEW_DELETE_CONFIRM).performClick()
        compose.waitUntil(timeoutMillis = 5_000) { writes.size == 3 }
        assertEquals("DELETE $MY_REVIEW", writes[2])
        waitForText("Your review was deleted.")
    }

    @Test
    fun `the listing row opens owner reviews, where reply, delete reply and Report act`() {
        var reply = "null"
        val nav =
            host(Destination.HubListing.route) { request ->
                val path = request.url.encodedPath
                when {
                    path == "/v1/hub/areas" -> ok("[]")
                    path == "/v1/hub/reviews" -> ok(owner(reply))
                    path == REPLY && request.method == HttpMethod.Put -> {
                        record(request)
                        reply = "pending"
                        ok(ownerReview(reply))
                    }
                    path == REPLY && request.method == HttpMethod.Delete -> {
                        record(request)
                        reply = "null"
                        respond("", HttpStatusCode.NoContent)
                    }
                    else -> ok(LISTING)
                }
            }

        waitForTag(TAG_HUB_REVIEWS)
        compose.onNodeWithTag(TAG_HUB_REVIEWS).performScrollTo().performClick()
        waitForTag(replyFieldTag(REVIEW))
        compose.runOnIdle { assertEquals(Destination.HubOwnerReviews.route, nav.currentDestination?.route) }
        // The server's label, verbatim; the neutral row from its nulls.
        compose.onNodeWithText("4.3 out of 5").assertExists()
        compose.onNodeWithText("Ratings appear once a class has 3 reviews.").assertExists()

        compose.onNodeWithTag(replyFieldTag(REVIEW)).performScrollTo().performTextInput("Thank you")
        compose.onNodeWithTag(replySendTag(REVIEW)).performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 5_000) { writes.isNotEmpty() }
        assertEquals("PUT $REPLY {\"body\":\"Thank you\"}", writes[0])
        waitForText("Awaiting review")

        compose.onNodeWithTag(replyDeleteTag(REVIEW)).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_REPLY_DELETE_CONFIRM).performClick()
        compose.waitUntil(timeoutMillis = 5_000) { writes.size == 2 }
        assertEquals("DELETE $REPLY", writes[1])
        waitForText("Your reply was deleted.")

        compose.onNodeWithTag(replyReportTag(REVIEW)).performScrollTo().performClick()
        waitForText("A guardian's review")
        compose.runOnIdle {
            assertEquals(Destination.HubReport.route, nav.currentDestination?.route)
            val args = nav.currentBackStackEntry?.arguments
            assertEquals("review", args?.getString(Destination.HubReport.ARG_KIND))
            assertEquals(REVIEW, args?.getString(Destination.HubReport.ARG_ID))
        }
    }

    @Test
    fun `a reply draft survives opening Report and coming back`() {
        // Found in review: the route loads again on return, and that load
        // wiped the draft [TC-8].
        val nav =
            host(Destination.HubOwnerReviews.route) { request ->
                when (request.url.encodedPath) {
                    "/v1/hub/reviews" -> ok(owner("null"))
                    else -> respond("", HttpStatusCode.NotFound)
                }
            }
        waitForTag(replyFieldTag(REVIEW))
        compose.onNodeWithTag(replyFieldTag(REVIEW)).performScrollTo().performTextInput("Thank you for")

        compose.onNodeWithTag(replyReportTag(REVIEW)).performScrollTo().performClick()
        waitForText("A guardian's review")
        compose.runOnIdle { nav.popBackStack() }

        waitForTag(replyFieldTag(REVIEW))
        compose.waitForIdle()
        compose.onNodeWithTag(replyFieldTag(REVIEW)).assertTextContains("Thank you for")
    }

    @Test
    fun `with reviews off the listing has no row and the screen draws no error`() {
        val asked = AtomicInteger()
        val nav =
            host(Destination.HubListing.route) { request ->
                when (request.url.encodedPath) {
                    "/v1/hub/areas" -> ok("[]")
                    "/v1/hub/reviews" -> {
                        asked.incrementAndGet()
                        respond(
                            """{"error":{"code":"HUB_REVIEWS_OFF","retryable":false,"message_key":"hub.review.off"}}""",
                            HttpStatusCode.NotFound,
                            json,
                        )
                    }
                    else -> ok(LISTING)
                }
            }
        waitForText("Batch listings")
        settleAfter(asked, 1)
        assertTrue(compose.onAllNodesWithTag(TAG_HUB_REVIEWS).fetchSemanticsNodes().isEmpty())

        compose.runOnIdle { nav.navigate(Destination.HubOwnerReviews.route) }
        settleAfter(asked, 2)
        compose.onNodeWithText("Reviews").assertExists()
        assertTrue(compose.onAllNodesWithTag(TAG_ERROR_RETRY).fetchSemanticsNodes().isEmpty())
        assertTrue(
            compose.onAllNodesWithText("Reviews are not available", substring = true).fetchSemanticsNodes().isEmpty(),
        )
    }

    /**
     * Wait for the server to have been asked [count] times, then let the
     * answer reach the screen. The off state draws nothing, so there is
     * no node to wait for; the main looper is idled until it has had
     * time to deliver the answer.
     */
    private fun settleAfter(asked: AtomicInteger, count: Int) {
        compose.waitUntil(timeoutMillis = 5_000) { asked.get() >= count }
        repeat(SETTLE_ROUNDS) {
            Thread.sleep(SETTLE_MILLIS)
            compose.waitForIdle()
        }
    }

    private companion object {
        const val HOME = "home"
        const val SETTLE_ROUNDS = 20
        const val SETTLE_MILLIS = 25L
        const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"
        const val REVIEW = "a1111111-1111-4111-8111-111111111111"
        const val MY_REVIEW = "/v1/hub/batches/$BATCH/my-review"
        const val REPLY = "/v1/hub/reviews/$REVIEW/reply"

        const val GUARDIAN_HOME = """{"children":[{"key":"c1","display_name":"Tasnim Akter","batch_count":1}]}"""

        const val REVIEWABLE =
            """[{"batch_id":"$BATCH","batch_title":"Physics 9","owner_public_name":"Rahima",""" +
                """"state":"eligible","eligible_from":null}]"""

        const val ELIGIBLE =
            """{"standing":"eligible","waiting_on":null,"eligible_from":null,"can_write":true,""" +
                """"edit_until":null,"review":null}"""

        const val PENDING =
            """{"standing":"eligible","waiting_on":null,"eligible_from":null,"can_write":true,""" +
                """"edit_until":"2026-12-19","review":{"rating":5,"body":"Clear teaching","status":"pending",""" +
                """"rejection_code":null,"tenure":"lt_6m","published_month":null,"reply_body":null}}"""

        const val LISTING =
            """{"status":"published","slug":"rahima","public_name":"Rahima","teaching_mode":[],
            "checklist":[],"publishable":true,"runs_classes":false,
            "consent_version_current":"2026-11-14","is_centre":false}"""

        fun ownerReview(status: String): String {
            val words = if (status == "null") "null" else "\"Thank you\""
            val state = if (status == "null") "null" else "\"$status\""
            return """{"id":"$REVIEW","batch_id":"$BATCH","rating":5,"body":"Patient with questions",""" +
                """"tenure":"6_12m","published_month":"2026-11","reply_body":null,"reply_month":null,""" +
                """"my_reply_status":$state,"my_reply_body":$words,"my_reply_rejection_code":null}"""
        }

        fun owner(status: String): String =
            """{"batches":[""" +
                """{"batch_id":"$BATCH","batch_title":"Physics 9","review_count":3,"average_tenths":43,""" +
                """"average_label":"4.3","distribution":[0,0,0,2,1]},""" +
                """{"batch_id":"b-2","batch_title":"Chemistry 10","review_count":null,"average_tenths":null,""" +
                """"average_label":null,"distribution":null}],""" +
                """"reviews":[${ownerReview(status)}]}"""
    }
}
