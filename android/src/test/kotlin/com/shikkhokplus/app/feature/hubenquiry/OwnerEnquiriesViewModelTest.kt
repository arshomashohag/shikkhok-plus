package com.shikkhokplus.app.feature.hubenquiry

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.HUB_OFFLINE_KEY
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The owner's inbox and one request: the listing editor's entry, the
 * answers offered (exactly `outcomes_allowed`), and what a failed answer
 * keeps [H5].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class OwnerEnquiriesViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun TestScope.detail(api: FakeEnquiryApi): OwnerEnquiryViewModel {
        val vm = OwnerEnquiryViewModel(api, "e-1")
        vm.load()
        advanceUntilIdle()
        return vm
    }

    private val OwnerEnquiryViewModel.view: OwnerEnquiryView
        get() = assertIs<OwnerEnquiryUiState.Ready>(state.value).view

    @Test
    fun `off hides entry`() = runTest(dispatcher) {
        val off = OwnerEnquiriesViewModel(FakeEnquiryApi().apply { inbox = listOf(enquiriesOff) })
        off.load()
        advanceUntilIdle()
        assertEquals(OwnerEnquiriesUiState.Off("hub.enquiry.off"), off.state.value)
        assertFalse(off.state.value.showsEntry)

        val failed = OwnerEnquiriesViewModel(FakeEnquiryApi().apply { inbox = listOf(AuthResult.TransportFailure) })
        failed.load()
        advanceUntilIdle()
        assertEquals(OwnerEnquiriesUiState.Error(HUB_OFFLINE_KEY, retryable = true), failed.state.value)
        assertFalse(failed.state.value.showsEntry)

        // An empty inbox still answered: the row is drawn.
        val empty = OwnerEnquiriesViewModel(FakeEnquiryApi())
        empty.load()
        advanceUntilIdle()
        assertTrue(empty.state.value.showsEntry)
    }

    @Test
    fun `the inbox is the server's rows in its order and a return keeps them while reading`() = runTest(dispatcher) {
        val rows = listOf(ownerEnquiry("e-2"), ownerEnquiry("e-1", status = "closed", outcome = "not_now"))
        val vm = OwnerEnquiriesViewModel(FakeEnquiryApi().apply { inbox = listOf(AuthResult.Ok(rows)) })
        vm.load()
        advanceUntilIdle()
        assertEquals(OwnerEnquiriesUiState.Ready(rows), vm.state.value)

        vm.load()
        assertIs<OwnerEnquiriesUiState.Ready>(vm.state.value)
    }

    @Test
    fun `owner contact shown only when shared`() = runTest(dispatcher) {
        // The client shows what the server sent and decides nothing: here the
        // shared phone, then nothing once the guardian stopped sharing.
        val api =
            FakeEnquiryApi().apply {
                reads = listOf(AuthResult.Ok(ownerEnquiry(phone = "+8801711000000")), AuthResult.Ok(ownerEnquiry()))
            }
        val vm = detail(api)
        assertEquals("+8801711000000", vm.view.enquiry.guardianPhone)

        vm.load()
        advanceUntilIdle()
        assertNull(vm.view.enquiry.guardianPhone)
        assertNull(vm.view.enquiry.guardianEmail)
    }

    @Test
    fun `the answers offered are exactly outcomes_allowed, in order`() {
        assertEquals(
            listOf(EnquiryOutcome.ADDED, EnquiryOutcome.NOT_NOW, EnquiryOutcome.CALL_US),
            ownerEnquiry(allowed = listOf("call_us", "not_now", "added")).offered,
        )
        assertEquals(listOf(EnquiryOutcome.NOT_NOW), ownerEnquiry(allowed = listOf("not_now", "later")).offered)
        assertTrue(ownerEnquiry(status = "closed").offered.isEmpty())
    }

    @Test
    fun `an answer is sent and the request shows it`() = runTest(dispatcher) {
        val closed = ownerEnquiry(status = "closed", outcome = "not_now")
        val api = FakeEnquiryApi().apply { closes = listOf(AuthResult.Ok(closed)) }
        val vm = detail(api)

        vm.answer(EnquiryOutcome.NOT_NOW)
        assertTrue(vm.view.closing)
        advanceUntilIdle()

        assertEquals(listOf("GET e-1", "CLOSE e-1 not_now"), api.calls)
        assertEquals(closed, vm.view.enquiry)
        assertTrue(vm.view.answered)
        vm.dismissNotice()
        assertFalse(vm.view.answered)
    }

    @Test
    fun `an answer the server does not offer is never sent`() = runTest(dispatcher) {
        val api = FakeEnquiryApi().apply { reads = listOf(AuthResult.Ok(ownerEnquiry(allowed = listOf("not_now")))) }
        val vm = detail(api)

        vm.answer(EnquiryOutcome.CALL_US)
        assertFalse(vm.answerAdded())
        advanceUntilIdle()
        assertTrue(api.calls.none { it.startsWith("CLOSE") })
    }

    @Test
    fun `a failed answer offers retry only when it can help`() = runTest(dispatcher) {
        val api =
            FakeEnquiryApi().apply {
                closes =
                    listOf(
                        AuthResult.TransportFailure,
                        refused("ENQUIRY_ALREADY_CLOSED", "hub.enquiry.already_closed"),
                    )
            }
        val vm = detail(api)

        vm.answer(EnquiryOutcome.CALL_US)
        advanceUntilIdle()
        assertEquals(EnquiryFailure(HUB_OFFLINE_KEY, canRetry = true), vm.view.failure)
        assertEquals(EnquiryOutcome.CALL_US, vm.view.retryOutcome)

        // A return to the screen does not wipe the failure with its Retry.
        vm.load()
        advanceUntilIdle()
        assertEquals(1, api.calls.count { it == "GET e-1" })

        vm.retry()
        advanceUntilIdle()
        assertEquals(listOf("CLOSE e-1 call_us", "CLOSE e-1 call_us"), api.calls.filter { it.startsWith("CLOSE") })
        assertEquals("hub.enquiry.already_closed", vm.view.failure?.messageKey)
        assertNull(vm.view.retryOutcome, "the server says trying again cannot help")
        vm.retry()
        advanceUntilIdle()
        assertEquals(2, api.calls.count { it.startsWith("CLOSE") })
    }

    @Test
    fun `adding answers added only while the server offers it`() = runTest(dispatcher) {
        val api = FakeEnquiryApi()
        val vm = detail(api)
        assertTrue(vm.answerAdded())
        advanceUntilIdle()
        assertEquals("CLOSE e-1 added", api.calls.last())

        val answered = detail(FakeEnquiryApi().apply { reads = listOf(AuthResult.Ok(ownerEnquiry(status = "closed"))) })
        assertFalse(answered.answerAdded(), "a request already answered is left as it is")
    }

    @Test
    fun `a request switched off or gone reads plainly, and offline offers retry`() = runTest(dispatcher) {
        val off = detail(FakeEnquiryApi().apply { reads = listOf(enquiriesOff) })
        assertEquals(OwnerEnquiryUiState.Unavailable("hub.enquiry.off"), off.state.value)
        val gone =
            detail(FakeEnquiryApi().apply { reads = listOf(refused("ENQUIRY_NOT_FOUND", "hub.enquiry.not_found")) })
        assertEquals(OwnerEnquiryUiState.Unavailable("hub.enquiry.not_found"), gone.state.value)
        gone.retryLoad()
        assertIs<OwnerEnquiryUiState.Unavailable>(gone.state.value)

        val offline =
            detail(
                FakeEnquiryApi().apply { reads = listOf(AuthResult.TransportFailure, AuthResult.Ok(ownerEnquiry())) },
            )
        assertEquals(OwnerEnquiryUiState.Error(HUB_OFFLINE_KEY), offline.state.value)
        offline.retryLoad()
        advanceUntilIdle()
        assertIs<OwnerEnquiryUiState.Ready>(offline.state.value)
    }

    @Test
    fun `nothing about a request is printed`() {
        val text = ownerEnquiry(phone = "+8801999999999", email = "sentinel@example.invalid").toString()
        listOf("+8801999999999", "sentinel@example.invalid", "Nadia", "Wants Physics").forEach {
            assertFalse(it in text, text)
        }
        assertFalse("Nadia" in myEnquiry().toString())
    }

    @Test
    fun `a failed quiet re-read of the inbox keeps the rows and the listing row`() = runTest(dispatcher) {
        val rows = listOf(ownerEnquiry("e-1"))
        val api =
            FakeEnquiryApi().apply {
                inbox = listOf(AuthResult.Ok(rows), AuthResult.TransportFailure, enquiriesOff)
            }
        val vm = OwnerEnquiriesViewModel(api)
        vm.load()
        vm.load()
        advanceUntilIdle()
        assertEquals(1, api.calls.count { it == "GET inbox" }, "one read at a time")

        vm.load()
        advanceUntilIdle()
        assertEquals(
            OwnerEnquiriesUiState.Ready(rows, EnquiryFailure(HUB_OFFLINE_KEY, canRetry = true)),
            vm.state.value,
        )
        assertTrue(vm.state.value.showsEntry)

        // Being switched off is not a dropped connection: it is said as such.
        vm.load()
        advanceUntilIdle()
        assertEquals(OwnerEnquiriesUiState.Off("hub.enquiry.off"), vm.state.value)
    }

    @Test
    fun `a late re-read cannot re-enable the answers while one is in flight`() = runTest(dispatcher) {
        val gate = CompletableDeferred<Unit>()
        val api =
            FakeEnquiryApi().apply {
                closeGate = gate
                closes = listOf(AuthResult.Ok(ownerEnquiry(status = "closed", outcome = "not_now")))
            }
        val vm = detail(api)

        // A return to the screen starts a re-read; the owner answers before it lands.
        vm.load()
        vm.answer(EnquiryOutcome.NOT_NOW)
        runCurrent()

        assertTrue(vm.view.closing, "the answers stay disabled until the close returns")
        assertEquals(1, api.calls.count { it == "GET e-1" }, "the late re-read was dropped")

        gate.complete(Unit)
        advanceUntilIdle()
        assertTrue(vm.view.answered)
        assertEquals("not_now", vm.view.enquiry.outcome)
    }

    @Test
    fun `after recreation a saved student's request is answered, not left stuck`() = runTest(dispatcher) {
        // Only the form's "saved" survived: this view model is fresh and reads the request again.
        val api = FakeEnquiryApi()
        val vm = OwnerEnquiryViewModel(api, "e-1")
        assertEquals(AfterSave.WAIT, vm.afterSave(), "nothing is decided before the request is read")
        vm.load()
        advanceUntilIdle()

        assertEquals(AfterSave.WAIT, vm.afterSave())
        assertTrue(vm.view.closing)
        assertEquals(AfterSave.WAIT, vm.afterSave(), "an answer in flight is not sent twice")
        advanceUntilIdle()
        assertEquals("CLOSE e-1 added", api.calls.last())
        assertEquals(1, api.calls.count { it.startsWith("CLOSE") })
        assertEquals(AfterSave.LEAVE, vm.afterSave())
    }

    @Test
    fun `after the save, a failed answer waits with its Retry, and a request already answered leaves`() =
        runTest(dispatcher) {
            val failing = detail(FakeEnquiryApi().apply { closes = listOf(AuthResult.TransportFailure) })
            failing.afterSave()
            advanceUntilIdle()
            assertEquals(AfterSave.WAIT, failing.afterSave())
            assertEquals(EnquiryOutcome.ADDED, failing.view.retryOutcome)

            val answered =
                detail(FakeEnquiryApi().apply { reads = listOf(AuthResult.Ok(ownerEnquiry(status = "closed"))) })
            assertEquals(AfterSave.LEAVE, answered.afterSave())
        }
}
