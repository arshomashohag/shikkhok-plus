package com.shikkhokplus.app.navigation

import androidx.compose.material3.Text
import androidx.compose.runtime.key
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.feature.hubenquiry.EnquiryLink
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
import java.util.Collections

/**
 * What the join-request route tests share [H5]: the real HTTP client over
 * a MockEngine, the record of every write, the app's shapes in small, and
 * the servers each side's screens talk to.
 *
 * **Wait on semantics, not on [writes].** Robolectric's main looper runs
 * only while the test waits on something Compose can see; a wait on the
 * request list alone does not let a response reach the screen.
 */
abstract class HubEnquiryRouteHarness {

    @get:Rule
    val compose = createComposeRule()

    protected val json = headersOf("Content-Type", ContentType.Application.Json.toString())

    /** Every write, as `METHOD path body`. */
    protected val writes: MutableList<String> = Collections.synchronizedList(mutableListOf<String>())

    protected fun MockRequestHandleScope.ok(
        body: String,
        status: HttpStatusCode = HttpStatusCode.OK,
    ): HttpResponseData = respond(body, status, json)

    /** A refusal the server says trying again can help with. */
    protected fun MockRequestHandleScope.unavailable(): HttpResponseData =
        respond(UNAVAILABLE, HttpStatusCode.ServiceUnavailable, json)

    protected fun record(request: HttpRequestData) {
        val body = (request.body as? TextContent)?.text.orEmpty()
        writes += "${request.method.value} ${request.url.encodedPath} $body".trim()
    }

    protected fun client(handle: MockRequestHandleScope.(HttpRequestData) -> HttpResponseData) =
        ApiClient.build("https://staging.example", MockEngine { handle(it) }, TokenStore.InMemory())

    protected fun waitForTag(tag: String) =
        compose.waitUntil(timeoutMillis = 5_000) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }

    protected fun waitForText(text: String) =
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText(text, substring = true).fetchSemanticsNodes().isNotEmpty()
        }

    /** The app's shape in small, as `MainActivity` composes it: sign-in or home, the hub routes, the link. */
    protected fun linkHost(
        link: () -> EnquiryLink?,
        signedIn: () -> Boolean,
        onOpened: () -> Unit,
        handle: MockRequestHandleScope.(HttpRequestData) -> HttpResponseData,
    ): () -> NavHostController {
        val client = client(handle)
        lateinit var current: NavHostController
        compose.setContent {
            ShikkhokTheme {
                key(signedIn()) {
                    val nav: NavHostController = rememberNavController()
                    current = nav
                    NavHost(nav, startDestination = if (signedIn()) HOME else SIGN_IN) {
                        composable(SIGN_IN) { Text(SIGN_IN) }
                        composable(HOME) { Text(HOME) }
                        hubRoutes(client, nav)
                    }
                    HubEnquiryLinkEffect(nav, signedIn(), link(), onOpened)
                }
            }
        }
        return { current }
    }

    /** A plain host over the hub routes, opened at [start]. */
    protected fun hubHost(
        start: String,
        handle: MockRequestHandleScope.(HttpRequestData) -> HttpResponseData,
    ): NavHostController {
        val client = client(handle)
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
        compose.runOnIdle { nav.navigate(start) }
        return nav
    }

    /**
     * The guardian's side: the target, the send, and the caller's own list.
     *
     * @param sends What each send answers, in turn; then a 201
     */
    protected fun MockRequestHandleScope.guardianSide(
        request: HttpRequestData,
        sends: MutableList<MockRequestHandleScope.() -> HttpResponseData> = mutableListOf(),
    ): HttpResponseData =
        when (request.url.encodedPath) {
            "/v1/hub/owners/rahima-apa/enquiry-target" -> ok(TARGET)
            "/v1/hub/owners/rahima-apa/enquiries" -> {
                record(request)
                sends.removeFirstOrNull()?.invoke(this) ?: ok(mine("e-1"), HttpStatusCode.Created)
            }
            MINE -> ok("[]")
            else -> respond("", HttpStatusCode.NotFound)
        }

    /**
     * The server as the owner's screens see it: the listing, its inbox, one
     * request and its answer, and the students the add-student form writes.
     *
     * @property offered Whether join requests are switched on
     * @property closeFails Whether the first answer fails, retryably
     * @property putFails Whether the first switch save fails, retryably
     * @property email Whether the guardian shared an email rather than a phone
     */
    protected inner class OwnerServer(
        val offered: Boolean,
        val closeFails: Boolean,
        val putFails: Boolean = false,
        val email: Boolean = false,
    ) {
        private var request = ownerEnquiry("open", email = email)
        private var closes = 0
        private var puts = 0

        fun handle(scope: MockRequestHandleScope, req: HttpRequestData): HttpResponseData {
            val path = req.url.encodedPath
            val post = req.method == HttpMethod.Post
            return when {
                path == "/v1/hub/listing" && req.method == HttpMethod.Put -> put(scope, req)
                path == "/v1/hub/listing" -> scope.ok(listing(offered, accepts = false))
                path == "/v1/hub/enquiries" -> scope.ok("[$request]")
                path == "/v1/hub/enquiries/$ENQUIRY" -> scope.ok(request)
                path == "/v1/hub/enquiries/$ENQUIRY/close" -> close(scope, req)
                path == "/v1/students" && post -> {
                    record(req)
                    scope.ok(STUDENT, HttpStatusCode.Created)
                }
                else -> scope.background(path)
            }
        }

        private fun put(scope: MockRequestHandleScope, req: HttpRequestData): HttpResponseData {
            record(req)
            puts++
            if (putFails && puts == 1) return scope.unavailable()
            return scope.ok(listing(offered, accepts = true))
        }

        private fun close(scope: MockRequestHandleScope, req: HttpRequestData): HttpResponseData {
            record(req)
            closes++
            if (closeFails && closes == 1) return scope.unavailable()
            val outcome = OUTCOME.find((req.body as? TextContent)?.text.orEmpty())?.groupValues?.get(1) ?: "added"
            request = ownerEnquiry("closed", outcome = outcome, email = email)
            return scope.ok(request)
        }
    }

    /** What every owner screen reads beside the request: areas, reviews (off), students and batches. */
    protected fun MockRequestHandleScope.background(path: String): HttpResponseData =
        when (path) {
            "/v1/hub/areas", "/v1/students" -> ok("[]")
            "/v1/hub/reviews" -> respond(OFF_REVIEWS, HttpStatusCode.NotFound, json)
            "/v1/batches" -> ok(BATCHES)
            else -> respond("", HttpStatusCode.NotFound)
        }

    /** The owner's side: the listing, its inbox, one request, and the add-student form. */
    protected fun ownerHost(
        server: OwnerServer = OwnerServer(offered = true, closeFails = false),
        start: String = Destination.HubListing.route,
    ): NavHostController {
        val client = client { server.handle(this, it) }
        lateinit var nav: NavHostController
        compose.setContent {
            ShikkhokTheme {
                nav = rememberNavController()
                NavHost(nav, startDestination = HOME) {
                    composable(HOME) { Text(HOME) }
                    hubRoutes(client, nav)
                    teacherStudentsRoutes(client, nav) {}
                }
            }
        }
        compose.runOnIdle { nav.navigate(start) }
        return nav
    }

    companion object {
        const val SIGN_IN = "sign-in"
        const val HOME = "home"
        const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"
        const val ENQUIRY = "e1111111-1111-4111-8111-111111111111"
        const val MINE = "/v1/me/hub/enquiries"
        const val GUARDIAN_PHONE = "+8801711000000"
        const val GUARDIAN_EMAIL = "guardian@example.com"

        /** The outcome in a close's body. */
        private val OUTCOME = Regex(""""outcome":"([a-z_]+)"""")

        const val TARGET =
            """{"owner_public_name":"Rahima","batch_title":"Physics 9","contact_kind":"phone","already_open":false}"""

        const val UNAVAILABLE =
            """{"error":{"code":"UNAVAILABLE","retryable":true,"message_key":"error.temporarily_unavailable"}}"""

        const val ALREADY_OPEN =
            """{"error":{"code":"ENQUIRY_ALREADY_OPEN","retryable":false,""" +
                """"message_key":"hub.enquiry.already_open"}}"""

        const val OFF = """{"error":{"code":"HUB_ENQUIRIES_OFF","retryable":false,"message_key":"hub.enquiry.off"}}"""
        const val OFF_REVIEWS =
            """{"error":{"code":"HUB_REVIEWS_OFF","retryable":false,"message_key":"hub.review.off"}}"""

        const val STUDENT =
            """{"student_id":"s-1","display_name":"Nadia","student_state":"none","guardian_state":"pending",""" +
                """"total_outstanding":"0.00","is_removable":true}"""

        const val BATCHES = """[{"id":"$BATCH","name":"Physics 9","subjects":["Physics"]}]"""

        fun mine(id: String, outcome: String? = null): String {
            val status = if (outcome == null) "open" else "closed"
            val answer = outcome?.let { "\"$it\"" } ?: "null"
            val phone = if (outcome == "call_us") "\"$GUARDIAN_PHONE\"" else "null"
            return """{"id":"$id","owner_public_name":"Rahima","batch_title":"Physics 9","student_name":"Nadia",""" +
                """"class_level":"class_8","message":null,"share_contact":true,"status":"$status",""" +
                """"outcome":$answer,"sent_on":"2026-11-19","owner_contact_phone":$phone}"""
        }

        fun ownerEnquiry(status: String, outcome: String = "added", email: Boolean = false): String {
            val open = status == "open"
            val answer = if (open) "null" else "\"$outcome\""
            val allowed = if (open) """["added","not_now","call_us"]""" else "[]"
            val phone = if (email) "null" else "\"$GUARDIAN_PHONE\""
            val mail = if (email) "\"$GUARDIAN_EMAIL\"" else "null"
            return """{"id":"$ENQUIRY","batch_id":"$BATCH","batch_title":"Physics 9","student_name":"Nadia",""" +
                """"class_level":"class_8","message":"Wants Physics","status":"$status","outcome":$answer,""" +
                """"received_at":"2026-11-19T06:00:00Z","guardian_phone":$phone,""" +
                """"guardian_email":$mail,"outcomes_allowed":$allowed}"""
        }

        fun listing(offered: Boolean, accepts: Boolean): String =
            """{"status":"published","slug":"rahima","public_name":"Rahima","teaching_mode":[],""" +
                """"checklist":[],"publishable":true,"runs_classes":false,""" +
                """"consent_version_current":"2026-11-14","is_centre":false,""" +
                """"accepts_enquiries":$accepts,"enquiries_offered":$offered}"""
    }
}
