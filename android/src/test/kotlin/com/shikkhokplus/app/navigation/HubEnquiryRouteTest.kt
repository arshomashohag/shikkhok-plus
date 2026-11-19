package com.shikkhokplus.app.navigation

import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.core.ui.TAG_FORM_GUARDIAN
import com.shikkhokplus.app.core.ui.TAG_FORM_NAME
import com.shikkhokplus.app.core.ui.TAG_FORM_SUBMIT
import com.shikkhokplus.app.feature.hubenquiry.EnquiryLink
import com.shikkhokplus.app.feature.hubenquiry.EnquiryOutcome
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_CLOSE_RETRY
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_DECLARE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_LEVEL
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_MESSAGE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_NAME
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_NO_SHARE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_SEND
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_SHARE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_WITHDRAW_CONFIRM
import com.shikkhokplus.app.feature.hubenquiry.ui.enquiryActionTag
import com.shikkhokplus.app.feature.hubenquiry.ui.myEnquiryWithdrawTag
import com.shikkhokplus.app.feature.hubenquiry.ui.ownerEnquiryRowTag
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_ENQUIRIES
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_ENQUIRIES_SWITCH
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_MY_ENQUIRIES
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
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Join requests, driven through the real routes with the real HTTP client
 * [H5].
 *
 * **A previous unit shipped an action the route never passed**, and the
 * view model's own test could not see it. So each action here starts where
 * a person starts -- the App Link, More's row, the listing editor's row --
 * and is proven by what reached the server or which destination opened.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class HubEnquiryRouteTest : HubEnquiryRouteHarness() {

    // ------------------------------------------------------------ the form

    @Test
    fun `an App Link opens the form, and send calls the API with the guardian's choices`() {
        var pending: EnquiryLink? by mutableStateOf(EnquiryLink("rahima-apa", BATCH))
        val targets = Collections.synchronizedList(mutableListOf<String>())
        linkHost({ pending }, { true }, { pending = null }) { request ->
            if (request.url.encodedPath.endsWith("/enquiry-target")) targets += request.url.encodedQuery
            guardianSide(request)
        }

        waitForText("To Rahima")
        compose.onNodeWithText("Physics 9").assertExists()
        assertEquals(listOf("batch_id=$BATCH"), targets.toList())
        // Nothing chosen for the guardian: Send waits for every choice.
        compose.onNodeWithTag(TAG_ENQUIRY_SEND).performScrollTo().assertIsNotEnabled()

        compose.onNodeWithTag(TAG_ENQUIRY_NAME).performScrollTo().performTextInput("Nadia")
        compose.onNodeWithTag(TAG_ENQUIRY_LEVEL).performScrollTo().performClick()
        compose.onNodeWithText("Class 8").performSemanticsAction(SemanticsActions.OnClick)
        compose.onNodeWithTag(TAG_ENQUIRY_MESSAGE).performScrollTo().performTextInput("Wants Physics")
        compose.onNodeWithText("Share my phone number with Rahima").assertExists()
        compose.onNodeWithTag(TAG_ENQUIRY_DECLARE).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_ENQUIRY_SEND).performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag(TAG_ENQUIRY_SHARE).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_ENQUIRY_SEND).performScrollTo().performClick()

        compose.waitUntil(timeoutMillis = 5_000) { writes.isNotEmpty() }
        assertEquals(
            "POST /v1/hub/owners/rahima-apa/enquiries " +
                """{"student_name":"Nadia","class_level":"class_8","message":"Wants Physics",""" +
                """"batch_id":"$BATCH","share_contact":true,"declares_adult_guardian":true}""",
            writes.single(),
        )
        waitForText("Your request was sent.")
        compose.runOnIdle { assertNull(pending, "the link was consumed, so it cannot open twice") }
    }

    @Test
    fun `a signed-out guardian is sent through sign-in and back to the form`() {
        var signedIn by mutableStateOf(false)
        var pending: EnquiryLink? by mutableStateOf(EnquiryLink("rahima-apa", null))
        linkHost({ pending }, { signedIn }, { pending = null }) { guardianSide(it) }

        compose.onNodeWithText(SIGN_IN).assertExists()
        assertEquals(EnquiryLink("rahima-apa", null), pending, "kept until there is someone to ask as")

        compose.runOnIdle { signedIn = true }

        waitForText("To Rahima")
        compose.runOnIdle { assertNull(pending) }
    }

    @Test
    fun `declining to share is sent as false`() {
        var pending: EnquiryLink? by mutableStateOf(EnquiryLink("rahima-apa", null))
        linkHost({ pending }, { true }, { pending = null }) { guardianSide(it) }

        waitForText("To Rahima")
        compose.onNodeWithTag(TAG_ENQUIRY_NAME).performScrollTo().performTextInput("Nadia")
        compose.onNodeWithTag(TAG_ENQUIRY_LEVEL).performScrollTo().performClick()
        compose.onNodeWithText("SSC").performSemanticsAction(SemanticsActions.OnClick)
        compose.onNodeWithTag(TAG_ENQUIRY_NO_SHARE).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_ENQUIRY_DECLARE).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_ENQUIRY_SEND).performScrollTo().performClick()

        compose.waitUntil(timeoutMillis = 5_000) { writes.isNotEmpty() }
        assertEquals(
            "POST /v1/hub/owners/rahima-apa/enquiries " +
                """{"student_name":"Nadia","class_level":"ssc","share_contact":false,"declares_adult_guardian":true}""",
            writes.single(),
        )
    }

    // ---------------------------------------------------------- my requests

    @Test
    fun `the More row opens my requests, and withdraw calls DELETE after its confirmation`() {
        var list = """[${mine("e-1")},${mine("e-2", outcome = "call_us")}]"""
        val client =
            client { request ->
                val path = request.url.encodedPath
                when {
                    path == "/v1/me" -> ok("""{"lenses":[],"phone":"+8801711111111"}""")
                    path == MINE && request.method == HttpMethod.Get -> ok(list)
                    path == "$MINE/e-1" && request.method == HttpMethod.Delete -> {
                        record(request)
                        list = "[${mine("e-2", outcome = "call_us")}]"
                        respond("", HttpStatusCode.NoContent)
                    }
                    else -> respond("", HttpStatusCode.NotFound)
                }
            }
        lateinit var nav: NavHostController
        compose.setContent {
            ShikkhokTheme {
                nav = rememberNavController()
                NavHost(nav, startDestination = HOME) {
                    composable(HOME) { Text(HOME) }
                    moreRoute(client, nav, SessionBinding(lens = Lens.GUARDIAN, onSwitch = null, onLensesChanged = {}))
                    hubRoutes(client, nav)
                }
            }
        }
        compose.runOnIdle { nav.navigate(Destination.Profile.route) }

        waitForTag(TAG_PROFILE_MY_ENQUIRIES)
        compose.onNodeWithTag(TAG_PROFILE_MY_ENQUIRIES).performScrollTo().performClick()
        waitForTag(myEnquiryWithdrawTag("e-1"))
        compose.runOnIdle { assertEquals(Destination.HubMyEnquiries.route, nav.currentDestination?.route) }
        compose.onNodeWithText("Waiting for an answer").assertExists()
        compose.onNodeWithText("Please call the teacher.").assertExists()
        compose.onNodeWithText("Call 01711-000000").assertExists()

        // Withdraw asks first; nothing is sent until it is confirmed.
        compose.onNodeWithTag(myEnquiryWithdrawTag("e-1")).performScrollTo().performClick()
        compose.onNodeWithText("This deletes your request completely.").assertExists()
        assertTrue(writes.isEmpty())
        compose.onNodeWithTag(TAG_ENQUIRY_WITHDRAW_CONFIRM).performClick()

        compose.waitUntil(timeoutMillis = 5_000) { writes.isNotEmpty() }
        assertEquals("DELETE $MINE/e-1", writes.single())
        waitForText("Request withdrawn.")
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithTag(myEnquiryWithdrawTag("e-1")).fetchSemanticsNodes().isEmpty()
        }
    }

    @Test
    fun `More shows no row while the server lists no request`() {
        val asked = AtomicInteger()
        val client =
            client { request ->
                when (request.url.encodedPath) {
                    "/v1/me" -> ok("""{"lenses":[],"phone":"+8801711111111"}""")
                    MINE -> {
                        asked.incrementAndGet()
                        ok("[]")
                    }
                    else -> respond("", HttpStatusCode.NotFound)
                }
            }
        lateinit var nav: NavHostController
        compose.setContent {
            ShikkhokTheme {
                nav = rememberNavController()
                NavHost(nav, startDestination = HOME) {
                    composable(HOME) { Text(HOME) }
                    moreRoute(client, nav, SessionBinding(lens = Lens.TEACHER, onSwitch = null, onLensesChanged = {}))
                }
            }
        }
        compose.runOnIdle { nav.navigate(Destination.Profile.route) }

        waitForText("Log out")
        compose.waitUntil(timeoutMillis = 5_000) { asked.get() >= 1 }
        compose.waitForIdle()
        assertTrue(compose.onAllNodesWithTag(TAG_PROFILE_MY_ENQUIRIES).fetchSemanticsNodes().isEmpty())
    }

    // -------------------------------------------------------- owner's inbox

    @Test
    fun `the listing row opens the inbox, then the request, and Add as student saves then answers added`() {
        val nav = ownerHost()

        waitForTag(TAG_HUB_ENQUIRIES)
        compose.onNodeWithTag(TAG_HUB_ENQUIRIES).performScrollTo().performClick()
        waitForTag(ownerEnquiryRowTag(ENQUIRY))
        compose.runOnIdle { assertEquals(Destination.HubOwnerEnquiries.route, nav.currentDestination?.route) }
        compose.onNodeWithText("Needs an answer").assertExists()
        // The list never shows the guardian's contact.
        assertTrue(compose.onAllNodesWithText("01711-000000", substring = true).fetchSemanticsNodes().isEmpty())

        compose.onNodeWithTag(ownerEnquiryRowTag(ENQUIRY)).performClick()
        waitForTag(enquiryActionTag(EnquiryOutcome.ADDED))
        compose.runOnIdle { assertEquals(Destination.HubOwnerEnquiry.route, nav.currentDestination?.route) }
        compose.onNodeWithText("01711-000000").assertExists()
        compose.onNodeWithText("Wants Physics").assertExists()

        compose.onNodeWithTag(enquiryActionTag(EnquiryOutcome.ADDED)).performScrollTo().performClick()
        waitForTag(TAG_FORM_NAME)
        compose.runOnIdle {
            assertEquals(Destination.NewStudent.route, nav.currentDestination?.route)
            assertEquals(ENQUIRY, nav.currentBackStackEntry?.arguments?.getString(Destination.NewStudent.ARG_ENQUIRY))
        }
        compose.onNodeWithText("Filled in from a join request. Check the details before saving.").assertExists()
        compose.onNodeWithTag(TAG_FORM_NAME).assertTextContains("Nadia")
        compose.onNodeWithTag(TAG_FORM_GUARDIAN).assertTextContains("01711-000000")
        assertTrue(writes.isEmpty(), "nothing is answered before the student is saved")

        compose.onNodeWithTag(TAG_FORM_SUBMIT).performScrollTo().performClick()

        // Back on the request, which now reads the answer. A semantics wait, not
        // the request list, so the main looper runs the save, the answer and Back.
        waitForText("Added as a student")
        compose.runOnIdle { assertEquals(Destination.HubOwnerEnquiry.route, nav.currentDestination?.route) }
        assertEquals(2, writes.size, "$writes")
        assertTrue(writes[0].startsWith("POST /v1/students "), writes[0])
        assertTrue(""""display_name":"Nadia"""" in writes[0], writes[0])
        assertTrue(""""guardian_phone":"01711-000000"""" in writes[0], writes[0])
        assertTrue(""""batch_id":"$BATCH"""" in writes[0], writes[0])
        assertEquals("""POST /v1/hub/enquiries/$ENQUIRY/close {"outcome":"added"}""", writes[1])
    }

    @Test
    fun `a failed answer after the save keeps the student saved and Retry answers alone`() {
        val nav = ownerHost(OwnerServer(offered = true, closeFails = true), Destination.NewStudent.of(null, ENQUIRY))

        waitForTag(TAG_FORM_NAME)
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performScrollTo().performClick()
        waitForTag(TAG_ENQUIRY_CLOSE_RETRY)
        compose.onNodeWithText("The student was saved, but the join request was not marked as answered.")
            .assertExists()
        // Saved once, and never again from this form.
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performScrollTo().assertIsNotEnabled()

        compose.onNodeWithTag(TAG_ENQUIRY_CLOSE_RETRY).performScrollTo().performClick()
        waitForText(HOME)
        compose.runOnIdle { assertEquals(HOME, nav.currentDestination?.route) }
        assertEquals(1, writes.count { it.startsWith("POST /v1/students ") }, "$writes")
        assertEquals(2, writes.count { it.startsWith("POST /v1/hub/enquiries/$ENQUIRY/close") }, "$writes")
    }

    @Test
    fun `the switch saves its one field, and while not offered there is no switch`() {
        ownerHost(OwnerServer(offered = true, closeFails = false))
        waitForTag(TAG_HUB_ENQUIRIES_SWITCH)
        compose.onNodeWithTag(TAG_HUB_ENQUIRIES_SWITCH).performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 5_000) { writes.isNotEmpty() }
        assertEquals("""PUT /v1/hub/listing {"accepts_enquiries":true}""", writes.single())
        compose.waitForIdle()
        compose.onNodeWithTag(TAG_HUB_ENQUIRIES_SWITCH).assertIsOn()
    }

    @Test
    fun `with join requests off the listing has neither switch nor row, and the inbox says so plainly`() {
        val asked = AtomicInteger()
        val client =
            client { req ->
                when (req.url.encodedPath) {
                    "/v1/hub/listing" -> ok(listing(offered = false, accepts = true))
                    "/v1/hub/areas" -> ok("[]")
                    "/v1/hub/reviews" -> respond(OFF_REVIEWS, HttpStatusCode.NotFound, json)
                    "/v1/hub/enquiries" -> {
                        asked.incrementAndGet()
                        respond(OFF, HttpStatusCode.NotFound, json)
                    }
                    else -> respond("", HttpStatusCode.NotFound)
                }
            }
        lateinit var nav: NavHostController
        compose.setContent {
            ShikkhokTheme {
                nav = rememberNavController()
                NavHost(nav, startDestination = HOME) {
                    composable(HOME) { Text(HOME) }
                    hubRoutes(client, nav)
                }
            }
        }
        compose.runOnIdle { nav.navigate(Destination.HubListing.route) }
        waitForText("Batch listings")
        compose.waitUntil(timeoutMillis = 5_000) { asked.get() >= 1 }
        compose.waitForIdle()
        assertTrue(compose.onAllNodesWithTag(TAG_HUB_ENQUIRIES).fetchSemanticsNodes().isEmpty())
        assertTrue(compose.onAllNodesWithTag(TAG_HUB_ENQUIRIES_SWITCH).fetchSemanticsNodes().isEmpty())

        compose.runOnIdle { nav.navigate(Destination.HubOwnerEnquiries.route) }
        waitForText("Join requests are not available right now.")
        assertTrue(compose.onAllNodesWithText("Try again").fetchSemanticsNodes().isEmpty())
    }
}
