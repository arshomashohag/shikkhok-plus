package com.shikkhokplus.app.navigation

import android.content.Intent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.feature.hubenquiry.EnquiryLink
import com.shikkhokplus.app.feature.hubenquiry.EnquiryOutcome
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_CLOSE_RETRY
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_CONTACT_EMAIL
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_CONTACT_PHONE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_DECLARE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_LEVEL
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_MINE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_NAME
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_RETRY
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_SEND
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_SHARE
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_WITHDRAW_CONFIRM
import com.shikkhokplus.app.feature.hubenquiry.ui.TAG_ENQUIRY_WITHDRAW_RETRY
import com.shikkhokplus.app.feature.hubenquiry.ui.enquiryActionTag
import com.shikkhokplus.app.feature.hubenquiry.ui.myEnquiryWithdrawTag
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_ENQUIRIES_SWITCH
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_ENQUIRIES_SWITCH_RETRY
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

/**
 * Every join-request action the route passes and the first route test did
 * not tap [H5, Task 9 review I-1]: the owner's two answers, the way from
 * the form to My join requests, one Retry per screen against a server that
 * fails once and then answers, and the call and email handed to the phone.
 *
 * Each is proven by what reached the server, which destination opened, or
 * which activity the phone was asked to start. A route that passed an
 * empty action fails here.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class HubEnquiryActionsRouteTest : HubEnquiryRouteHarness() {

    /** Open one request for its owner. */
    private fun request(server: OwnerServer = OwnerServer(offered = true, closeFails = false)) =
        ownerHost(server, Destination.HubOwnerEnquiry.of(ENQUIRY)).also {
            waitForTag(enquiryActionTag(EnquiryOutcome.NOT_NOW))
        }

    // ------------------------------------------------------- the answers

    @Test
    fun `Not now sends not_now and the request reads its answer`() {
        request()

        compose.onNodeWithTag(enquiryActionTag(EnquiryOutcome.NOT_NOW)).performScrollTo().performClick()

        waitForText("Answered: not now")
        assertEquals(listOf("""POST /v1/hub/enquiries/$ENQUIRY/close {"outcome":"not_now"}"""), writes.toList())
    }

    @Test
    fun `Ask them to call sends call_us while it is offered`() {
        request()

        compose.onNodeWithTag(enquiryActionTag(EnquiryOutcome.CALL_US)).performScrollTo().performClick()

        waitForText("Asked them to call you")
        assertEquals(listOf("""POST /v1/hub/enquiries/$ENQUIRY/close {"outcome":"call_us"}"""), writes.toList())
    }

    @Test
    fun `a failed answer on the request offers Retry, which sends it again`() {
        request(OwnerServer(offered = true, closeFails = true))

        compose.onNodeWithTag(enquiryActionTag(EnquiryOutcome.NOT_NOW)).performScrollTo().performClick()
        waitForTag(TAG_ENQUIRY_CLOSE_RETRY)
        compose.onNodeWithTag(TAG_ENQUIRY_CLOSE_RETRY).performScrollTo().performClick()

        waitForText("Answered: not now")
        assertEquals(
            List(2) { """POST /v1/hub/enquiries/$ENQUIRY/close {"outcome":"not_now"}""" },
            writes.toList(),
        )
    }

    // ---------------------------------------------------- dial and email

    @Test
    fun `the guardian's shared phone is handed to the dialler`() {
        request()

        compose.onNodeWithTag(TAG_ENQUIRY_CONTACT_PHONE).performScrollTo().performClick()

        val started = assertNotNull(shadowOf(RuntimeEnvironment.getApplication()).nextStartedActivity)
        assertEquals(Intent.ACTION_DIAL, started.action)
        assertEquals("tel:$GUARDIAN_PHONE", started.dataString)
    }

    @Test
    fun `the guardian's shared email is handed to the mail app`() {
        request(OwnerServer(offered = true, closeFails = false, email = true))

        compose.onNodeWithTag(TAG_ENQUIRY_CONTACT_EMAIL).performScrollTo().performClick()

        val started = assertNotNull(shadowOf(RuntimeEnvironment.getApplication()).nextStartedActivity)
        assertEquals(Intent.ACTION_SENDTO, started.action)
        assertEquals("mailto:$GUARDIAN_EMAIL", started.dataString)
    }

    @Test
    fun `the owner's published number on a call_us answer is handed to the dialler`() {
        hubHost(Destination.HubMyEnquiries.route) { request ->
            if (request.url.encodedPath == MINE) ok("[${mine("e-1", outcome = "call_us")}]") else notFound()
        }
        waitForText("Call 01711-000000")

        compose.onNodeWithText("Call 01711-000000").performScrollTo().performClick()

        val started = assertNotNull(shadowOf(RuntimeEnvironment.getApplication()).nextStartedActivity)
        assertEquals(Intent.ACTION_DIAL, started.action)
        assertEquals("tel:$GUARDIAN_PHONE", started.dataString)
    }

    // ---------------------------------------------------------- the form

    /** Open the form from its link and fill every required choice. */
    private fun filledForm(sends: MutableList<MockRequestHandleScope.() -> HttpResponseData>) =
        run {
            var pending: EnquiryLink? by mutableStateOf(EnquiryLink("rahima-apa", null))
            val nav = linkHost({ pending }, { true }, { pending = null }) { guardianSide(it, sends) }
            waitForText("To Rahima")
            compose.onNodeWithTag(TAG_ENQUIRY_NAME).performScrollTo().performTextInput("Nadia")
            compose.onNodeWithTag(TAG_ENQUIRY_LEVEL).performScrollTo().performClick()
            compose.onNodeWithText("Class 8").performSemanticsAction(SemanticsActions.OnClick)
            compose.onNodeWithTag(TAG_ENQUIRY_SHARE).performScrollTo().performClick()
            compose.onNodeWithTag(TAG_ENQUIRY_DECLARE).performScrollTo().performClick()
            compose.onNodeWithTag(TAG_ENQUIRY_SEND).performScrollTo().performClick()
            nav
        }

    @Test
    fun `a failed send offers Retry, which sends what is on screen again`() {
        filledForm(mutableListOf<MockRequestHandleScope.() -> HttpResponseData>({ unavailable() }))

        waitForTag(TAG_ENQUIRY_RETRY)
        compose.onNodeWithTag(TAG_ENQUIRY_RETRY).performScrollTo().performClick()

        waitForText("Your request was sent.")
        assertEquals(2, writes.size, "$writes")
        assertEquals(writes[0], writes[1])
    }

    @Test
    fun `a request already open at send time leads to My join requests`() {
        val nav =
            filledForm(
                mutableListOf<MockRequestHandleScope.() -> HttpResponseData>(
                    { respond(ALREADY_OPEN, HttpStatusCode.Conflict, json) },
                ),
            )

        waitForTag(TAG_ENQUIRY_MINE)
        compose.onNodeWithTag(TAG_ENQUIRY_MINE).performScrollTo().performClick()

        waitForText("You have no join requests.")
        compose.runOnIdle { assertEquals(Destination.HubMyEnquiries.route, nav().currentDestination?.route) }
    }

    // ------------------------------------------------------- withdrawal

    @Test
    fun `a failed withdrawal offers Retry, which asks again and then withdraws`() {
        var deletes = 0
        hubHost(Destination.HubMyEnquiries.route) { request ->
            val path = request.url.encodedPath
            when {
                path == MINE -> ok(if (deletes < 2) "[${mine("e-1")}]" else "[]")
                path == "$MINE/e-1" && request.method == HttpMethod.Delete -> {
                    record(request)
                    deletes++
                    if (deletes == 1) unavailable() else respond("", HttpStatusCode.NoContent)
                }
                else -> notFound()
            }
        }
        waitForTag(myEnquiryWithdrawTag("e-1"))
        compose.onNodeWithTag(myEnquiryWithdrawTag("e-1")).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_ENQUIRY_WITHDRAW_CONFIRM).performClick()

        waitForTag(TAG_ENQUIRY_WITHDRAW_RETRY)
        compose.onNodeWithTag(TAG_ENQUIRY_WITHDRAW_RETRY).performScrollTo().performClick()
        // Retry asks again; nothing is deleted from anywhere but the confirmation.
        waitForTag(TAG_ENQUIRY_WITHDRAW_CONFIRM)
        compose.onNodeWithTag(TAG_ENQUIRY_WITHDRAW_CONFIRM).performClick()

        waitForText("Request withdrawn.")
        assertEquals(List(2) { "DELETE $MINE/e-1" }, writes.toList())
    }

    // ---------------------------------------------------------- the switch

    @Test
    fun `a failed switch offers Retry, which saves it again`() {
        ownerHost(OwnerServer(offered = true, closeFails = false, putFails = true))
        waitForTag(TAG_HUB_ENQUIRIES_SWITCH)

        compose.onNodeWithTag(TAG_HUB_ENQUIRIES_SWITCH).performScrollTo().performClick()
        waitForTag(TAG_HUB_ENQUIRIES_SWITCH_RETRY)
        compose.onNodeWithTag(TAG_HUB_ENQUIRIES_SWITCH_RETRY).performScrollTo().performClick()

        compose.waitUntil(timeoutMillis = 5_000) {
            runCatching { compose.onNodeWithTag(TAG_HUB_ENQUIRIES_SWITCH).assertIsOn() }.isSuccess
        }
        assertEquals(List(2) { """PUT /v1/hub/listing {"accepts_enquiries":true}""" }, writes.toList())
    }

    private fun MockRequestHandleScope.notFound(): HttpResponseData = respond("", HttpStatusCode.NotFound)
}
