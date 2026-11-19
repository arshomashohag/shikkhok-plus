package com.shikkhokplus.app.feature.hubenquiry

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.ClassLevel
import com.shikkhokplus.app.feature.hublisting.HUB_OFFLINE_KEY
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
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
 * The "Ask to join" form: what it reads first, what it requires before
 * Send does anything, what it sends, and what a failure keeps [H5, TC-8].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class EnquiryFormViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun TestScope.loaded(
        api: FakeEnquiryApi,
        link: EnquiryLink = EnquiryLink("rahima", BATCH),
    ): EnquiryFormViewModel {
        val vm = EnquiryFormViewModel(api, link)
        vm.load()
        advanceUntilIdle()
        return vm
    }

    /** Fill every required field: a name, a class, a share choice and the declaration. */
    private fun EnquiryFormViewModel.fill(share: Boolean) {
        editName("  Nadia  ")
        pickLevel(ClassLevel.CLASS_8)
        editMessage(" Wants Physics ")
        chooseShare(share)
        declare(true)
    }

    private val EnquiryFormViewModel.form: EnquiryForm
        get() = assertIs<EnquiryFormUiState.Ready>(state.value).form

    @Test
    fun `send success`() = runTest(dispatcher) {
        val api = FakeEnquiryApi()
        val vm = loaded(api)
        assertEquals(listOf("GET target rahima $BATCH"), api.calls)
        assertEquals(target(), vm.form.target)

        vm.fill(share = true)
        vm.send()
        assertIs<EnquiryFormUiState.Sending>(vm.state.value)
        advanceUntilIdle()

        assertEquals(EnquiryFormUiState.Sent(target()), vm.state.value)
        assertEquals(
            listOf(
                EnquiryWrite(
                    studentName = "Nadia",
                    classLevel = "class_8",
                    message = "Wants Physics",
                    batchId = BATCH,
                    shareContact = true,
                    declaresAdultGuardian = true,
                ),
            ),
            api.sent,
        )
    }

    @Test
    fun `share choice required`() = runTest(dispatcher) {
        val api = FakeEnquiryApi()
        val vm = loaded(api)

        vm.editName("Nadia")
        vm.pickLevel(ClassLevel.CLASS_8)
        vm.declare(true)
        assertNull(vm.form.share, "sharing is never a default")
        assertFalse(vm.form.canSend)
        vm.send()
        advanceUntilIdle()
        assertTrue(api.sent.isEmpty(), "nothing is sent without a share choice")

        // Declining is a choice too, and is sent as false.
        vm.chooseShare(false)
        assertTrue(vm.form.canSend)
        vm.declare(false)
        assertFalse(vm.form.canSend, "the declaration is required as well")
        vm.declare(true)
        vm.send()
        advanceUntilIdle()
        assertEquals(false, api.sent.single().shareContact)
        assertNull(api.sent.single().message, "a blank message is sent as none")
    }

    @Test
    fun `a blank name or no class keeps Send disabled`() = runTest(dispatcher) {
        val vm = loaded(FakeEnquiryApi())
        vm.chooseShare(true)
        vm.declare(true)
        vm.editName("   ")
        vm.pickLevel(ClassLevel.SSC)
        assertFalse(vm.form.canSend)
        vm.editName("N".repeat(STUDENT_NAME_MAX + 5))
        assertEquals(STUDENT_NAME_MAX, vm.form.name.length, "the server's limit")
        vm.editMessage("m".repeat(ENQUIRY_MESSAGE_MAX + 5))
        assertEquals(ENQUIRY_MESSAGE_MAX, vm.form.message.length)
        assertTrue(vm.form.canSend)
    }

    @Test
    fun `already open`() = runTest(dispatcher) {
        // Said by the target read: no form at all.
        val open = loaded(FakeEnquiryApi().apply { targets = listOf(AuthResult.Ok(target(alreadyOpen = true))) })
        assertEquals(EnquiryFormUiState.AlreadyOpen(target(alreadyOpen = true)), open.state.value)

        // Refused at send time, from another device: the way to it, and no Retry.
        val api =
            FakeEnquiryApi().apply {
                sends = listOf(refused("ENQUIRY_ALREADY_OPEN", "hub.enquiry.already_open", retryable = false))
            }
        val vm = loaded(api)
        vm.fill(share = true)
        vm.send()
        advanceUntilIdle()
        val failure = vm.form.failure
        assertEquals(EnquiryFailure("hub.enquiry.already_open", canRetry = false, alreadyOpen = true), failure)
    }

    @Test
    fun `contact refused keeps text`() = runTest(dispatcher) {
        val api =
            FakeEnquiryApi().apply {
                sends = listOf(refused("ENQUIRY_CONTAINS_CONTACT", "hub.enquiry.contains_contact"))
            }
        val vm = loaded(api)
        vm.fill(share = false)
        vm.editMessage("Call 01711000000")
        vm.send()
        advanceUntilIdle()

        val form = vm.form
        assertEquals(EnquiryFailure("hub.enquiry.contains_contact", canRetry = false), form.failure)
        assertEquals("Call 01711000000", form.message, "what was typed stays, so the number can be taken out")
        assertEquals("  Nadia  ", form.name)
        assertEquals(false, form.share)
        assertTrue(form.declared)

        // Not retryable: Retry sends nothing.
        vm.retry()
        advanceUntilIdle()
        assertEquals(1, api.sent.size)
    }

    @Test
    fun `network failure keeps text and offers retry`() = runTest(dispatcher) {
        val api = FakeEnquiryApi().apply { sends = listOf(AuthResult.TransportFailure, AuthResult.Ok(myEnquiry())) }
        val vm = loaded(api)
        vm.fill(share = true)
        vm.send()
        advanceUntilIdle()

        val form = vm.form
        assertEquals(EnquiryFailure(HUB_OFFLINE_KEY, canRetry = true), form.failure)
        assertEquals(ClassLevel.CLASS_8, form.level)
        assertEquals(" Wants Physics ", form.message)

        vm.retry()
        advanceUntilIdle()
        assertIs<EnquiryFormUiState.Sent>(vm.state.value)
        assertEquals(2, api.sent.size)
        assertEquals(api.sent[0], api.sent[1], "Retry sends what is on screen")
    }

    @Test
    fun `a return to the screen never wipes what was typed`() = runTest(dispatcher) {
        val api = FakeEnquiryApi()
        val vm = loaded(api)
        vm.editName("Nadia")

        vm.load()
        advanceUntilIdle()

        assertEquals("Nadia", vm.form.name)
        assertEquals(1, api.calls.count { it.startsWith("GET target") })
    }

    @Test
    fun `off and a target not taking requests read as unavailable, with no form`() = runTest(dispatcher) {
        val off = loaded(FakeEnquiryApi().apply { targets = listOf(enquiriesOff) })
        assertEquals(EnquiryFormUiState.Unavailable("hub.enquiry.off"), off.state.value)

        val gone =
            loaded(
                FakeEnquiryApi().apply {
                    targets = listOf(refused("ENQUIRY_TARGET_NOT_FOUND", "hub.enquiry.target_not_found"))
                },
            )
        assertEquals(EnquiryFormUiState.Unavailable("hub.enquiry.target_not_found"), gone.state.value)
        off.retryLoad()
        advanceUntilIdle()
        assertIs<EnquiryFormUiState.Unavailable>(off.state.value, "nothing to retry")
    }

    @Test
    fun `an offline target read offers retry`() = runTest(dispatcher) {
        val api = FakeEnquiryApi().apply { targets = listOf(AuthResult.TransportFailure, AuthResult.Ok(target())) }
        val vm = loaded(api)
        assertEquals(EnquiryFormUiState.Error(HUB_OFFLINE_KEY), vm.state.value)

        vm.retryLoad()
        advanceUntilIdle()
        assertIs<EnquiryFormUiState.Ready>(vm.state.value)
    }

    @Test
    fun `a link with no owner or a malformed batch is invalid and reads nothing`() = runTest(dispatcher) {
        listOf(EnquiryLink(null, null), EnquiryLink(" ", null), EnquiryLink("rahima", "not-a-uuid")).forEach {
            val api = FakeEnquiryApi()
            val vm = loaded(api, it)
            assertEquals(EnquiryFormUiState.Invalid, vm.state.value, "$it")
            vm.send()
            advanceUntilIdle()
            assertTrue(api.calls.isEmpty(), "$it")
        }
        // An owner alone asks the owner as a whole.
        val api = FakeEnquiryApi()
        loaded(api, EnquiryLink("rahima", null))
        assertEquals(listOf("GET target rahima null"), api.calls)
    }

    @Test
    fun `nothing changes while a send is in flight`() = runTest(dispatcher) {
        val api = FakeEnquiryApi()
        val vm = loaded(api)
        vm.fill(share = true)
        vm.send()
        vm.editName("Other")
        vm.send()
        advanceUntilIdle()
        assertEquals(1, api.sent.size)
        assertEquals("Nadia", api.sent.single().studentName)
    }

    @Test
    fun `the form never prints what a family typed`() {
        val form = EnquiryForm(target(), name = "Sentinel Child", message = "sentinel message")
        val body = EnquiryWrite("Sentinel Child", "class_8", "sentinel message", null, true, true)
        listOf(form.toString(), body.toString()).forEach { text ->
            assertFalse("Sentinel" in text || "sentinel" in text, text)
        }
    }

    private companion object {
        const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"
    }
}
