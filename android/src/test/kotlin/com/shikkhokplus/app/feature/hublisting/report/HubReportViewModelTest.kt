package com.shikkhokplus.app.feature.hublisting.report

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.OpenApi
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.HUB_OFFLINE_KEY
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Reporting a public hub page: the target is the link's, a malformed link
 * sends nothing, a dropped connection keeps the input and offers Retry,
 * and each refusal carries the server's message without a Retry.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HubReportViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    /** Records each report and answers with the queued results, the last repeating. */
    private class FakeReportApi(vararg results: AuthResult<Unit>) : HubReportApi {
        val sent = mutableListOf<HubReportRequest>()
        private val queue = ArrayDeque(results.toList().ifEmpty { listOf(AuthResult.Ok(Unit)) })

        override suspend fun file(request: HubReportRequest): AuthResult<Unit> {
            sent += request
            return if (queue.size > 1) queue.removeFirst() else queue.first()
        }
    }

    private fun refused(code: String, key: String, retryable: Boolean = false): AuthResult<Unit> =
        AuthResult.Refused(ErrorEnvelope(ErrorBody(code, retryable = retryable, messageKey = key)))

    @Test
    fun opens_from_the_link_and_sends_reason_and_note() = runTest(dispatcher) {
        val api = FakeReportApi()
        val vm = HubReportViewModel(api, ReportLink("batch_listing", BATCH))

        assertEquals(ReportTarget(ReportKind.BATCH_LISTING, BATCH), vm.state.value.target)
        assertFalse(vm.state.value.canSend, "nothing to send before a reason is chosen")
        vm.pickReason(ReportReason.FAKE)
        vm.editNote("  Same photo as another centre ")
        vm.send()
        advanceUntilIdle()

        assertEquals(
            listOf(HubReportRequest("batch_listing", BATCH, "fake", "Same photo as another centre")),
            api.sent,
        )
        assertTrue(vm.state.value.sent)
        assertNull(vm.state.value.failure)
        assertFalse(vm.state.value.canSend, "a sent report is not sent again")
    }

    @Test
    fun a_photo_link_reports_the_photo() = runTest(dispatcher) {
        val api = FakeReportApi()
        val vm = HubReportViewModel(api, ReportLink("media", PHOTO))

        assertEquals(ReportTarget(ReportKind.MEDIA, PHOTO), vm.state.value.target)
        vm.pickReason(ReportReason.CHILD_SAFETY)
        vm.send()
        advanceUntilIdle()

        assertEquals(listOf(HubReportRequest("media", PHOTO, "child_safety", null)), api.sent)
        assertTrue(vm.state.value.sent)
    }

    @Test
    fun a_blank_note_is_not_sent() = runTest(dispatcher) {
        val api = FakeReportApi()
        val vm = HubReportViewModel(api, ReportLink("owner_listing", OWNER))

        vm.pickReason(ReportReason.PERSONAL_INFO)
        vm.editNote("   ")
        vm.send()
        advanceUntilIdle()

        assertEquals(listOf(HubReportRequest("owner_listing", OWNER, "personal_info", null)), api.sent)
    }

    @Test
    fun the_note_stops_at_the_servers_limit() {
        val vm = HubReportViewModel(FakeReportApi(), ReportLink("owner_listing", OWNER))

        vm.editNote("x".repeat(NOTE_MAX + 20))

        assertEquals(NOTE_MAX, vm.state.value.note.length)
    }

    @Test
    fun rejects_bad_kind_or_id_without_a_request() = runTest(dispatcher) {
        val bad =
            listOf(
                ReportLink("reviews", OWNER),
                ReportLink("media", "photo-1"),
                ReportLink(null, OWNER),
                ReportLink("owner_listing", null),
                ReportLink("owner_listing", "sumi-apa"),
                ReportLink("owner_listing", "${OWNER}x"),
                ReportLink("", ""),
            )
        bad.forEach { link ->
            val api = FakeReportApi()
            val vm = HubReportViewModel(api, link)

            vm.pickReason(ReportReason.OTHER)
            vm.send()
            advanceUntilIdle()

            assertNull(vm.state.value.target, "$link")
            assertFalse(vm.state.value.canSend, "$link")
            assertTrue(api.sent.isEmpty(), "$link sent a request")
        }
    }

    @Test
    fun failure_keeps_input_and_offers_retry() = runTest(dispatcher) {
        val api = FakeReportApi(AuthResult.TransportFailure, AuthResult.Ok(Unit))
        val vm = HubReportViewModel(api, ReportLink("owner_listing", OWNER))
        vm.pickReason(ReportReason.MISLEADING)
        vm.editNote("Claims a board result it never had")

        vm.send()
        advanceUntilIdle()

        val failed = vm.state.value
        assertEquals(HUB_OFFLINE_KEY, failed.failure?.messageKey)
        assertTrue(failed.failure?.canRetry == true)
        assertEquals(ReportReason.MISLEADING, failed.reason)
        assertEquals("Claims a board result it never had", failed.note)
        assertFalse(failed.sent)

        vm.retry()
        advanceUntilIdle()

        val body = HubReportRequest("owner_listing", OWNER, "misleading", "Claims a board result it never had")
        assertEquals(listOf(body, body), api.sent)
        assertTrue(vm.state.value.sent)
        assertNull(vm.state.value.failure)
    }

    @Test
    fun each_refusal_names_its_message_and_offers_no_retry() = runTest(dispatcher) {
        val refusals =
            mapOf(
                refused("REPORT_TARGET_NOT_FOUND", "hub.report_target_not_found") to "hub.report_target_not_found",
                refused("REPORT_ALREADY_FILED", "hub.report_already_filed") to "hub.report_already_filed",
                refused("HUB_REPORT_CEILING", "hub.report_ceiling") to "hub.report_ceiling",
            )
        refusals.forEach { (result, key) ->
            val api = FakeReportApi(result)
            val vm = HubReportViewModel(api, ReportLink("owner_listing", OWNER))
            vm.pickReason(ReportReason.ABUSIVE)
            vm.send()
            advanceUntilIdle()

            assertEquals(key, vm.state.value.failure?.messageKey)
            assertFalse(vm.state.value.failure?.canRetry ?: true, key)
            vm.retry()
            advanceUntilIdle()
            assertEquals(1, api.sent.size, "$key was retried")
            assertEquals(ReportReason.ABUSIVE, vm.state.value.reason)
        }
    }

    @Test
    fun the_reasons_and_note_limit_are_the_servers() {
        val request = schema("HubReportRequest")["properties"]!!.jsonObject
        val reasons =
            OpenApi.resolve(request["reason"]!!.jsonObject)["enum"]!!.jsonArray.map { it.jsonPrimitive.content }
        val note =
            request["note"]!!.jsonObject["anyOf"]!!.jsonArray.firstNotNullOf {
                it.jsonObject["maxLength"]?.jsonPrimitive?.intOrNull
            }

        assertEquals(reasons.toSet(), ReportReason.entries.map { it.wire }.toSet())
        assertEquals(ReportReason.entries.size, ReportReason.entries.map { it.wire }.toSet().size)
        assertEquals(note, NOTE_MAX)
    }

    @Test
    fun the_kinds_are_the_servers_and_a_reply_is_reported_by_its_review() = runTest(dispatcher) {
        val kinds =
            OpenApi.resolve(schema("HubReportRequest")["properties"]!!.jsonObject["target_kind"]!!.jsonObject)["enum"]!!
                .jsonArray.map { it.jsonPrimitive.content }
        assertEquals(kinds.toSet(), ReportKind.entries.map { it.wire }.toSet())

        val api = FakeReportApi()
        val vm = HubReportViewModel(api, ReportLink("reply", PHOTO))
        assertEquals(ReportTarget(ReportKind.REPLY, PHOTO), vm.state.value.target)
        vm.pickReason(ReportReason.ABUSIVE)
        vm.send()
        advanceUntilIdle()
        assertEquals(listOf(HubReportRequest("reply", PHOTO, "abusive", null)), api.sent)
    }

    private fun schema(name: String): JsonObject =
        OpenApi.spec["components"]!!.jsonObject["schemas"]!!.jsonObject[name]!!.jsonObject

    private companion object {
        const val OWNER = "6f1c2b0e-3a4d-4e5f-8a9b-0c1d2e3f4a5b"
        const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"
        const val PHOTO = "a1111111-1111-4111-8111-111111111111"
    }
}
