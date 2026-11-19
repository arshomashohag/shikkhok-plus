package com.shikkhokplus.app.feature.hubenquiry

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.HUB_OFFLINE_KEY
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
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
 * The guardian's own join requests, More's entry to them, and withdrawal,
 * which deletes completely and is sent only from its confirmation [H5].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class MyEnquiriesViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val ready: (MyEnquiriesViewModel) -> MyEnquiriesUiState.Ready = {
        assertIs<MyEnquiriesUiState.Ready>(it.state.value)
    }

    @Test
    fun `withdraw confirmed`() = runTest(dispatcher) {
        val api =
            FakeEnquiryApi().apply {
                mine =
                    listOf(
                        AuthResult.Ok(listOf(myEnquiry("e-1"), myEnquiry("e-2"))),
                        AuthResult.Ok(listOf(myEnquiry("e-2"))),
                    )
            }
        val vm = MyEnquiriesViewModel(api)
        vm.load()
        advanceUntilIdle()

        // Asking opens the confirmation; nothing is sent, and Cancel sends nothing.
        vm.askWithdraw("e-1")
        assertEquals("e-1", ready(vm).confirming)
        vm.cancelWithdraw()
        assertNull(ready(vm).confirming)
        assertTrue(api.calls.none { it.startsWith("DELETE") })

        vm.askWithdraw("e-1")
        vm.confirmWithdraw()
        assertTrue(ready(vm).withdrawing)
        advanceUntilIdle()

        assertEquals(listOf("GET mine", "DELETE e-1", "GET mine"), api.calls)
        assertEquals(listOf("e-2"), ready(vm).rows.map { it.id })
        assertTrue(ready(vm).withdrawn)
        vm.dismissNotice()
        assertFalse(ready(vm).withdrawn)
    }

    @Test
    fun `a failed withdrawal keeps the row and Retry asks again`() = runTest(dispatcher) {
        val api =
            FakeEnquiryApi().apply {
                mine = listOf(AuthResult.Ok(listOf(myEnquiry("e-1"))))
                withdrawals = listOf(AuthResult.TransportFailure)
            }
        val vm = MyEnquiriesViewModel(api)
        vm.load()
        advanceUntilIdle()
        vm.askWithdraw("e-1")
        vm.confirmWithdraw()
        advanceUntilIdle()

        assertEquals(WithdrawFailure("e-1", EnquiryFailure(HUB_OFFLINE_KEY, canRetry = true)), ready(vm).failure)
        assertEquals(listOf("e-1"), ready(vm).rows.map { it.id })

        // A return to the screen does not wipe the failure with its Retry.
        vm.load()
        advanceUntilIdle()
        assertEquals(1, api.calls.count { it == "GET mine" })

        vm.retryWithdraw()
        assertEquals("e-1", ready(vm).confirming, "Retry reopens the confirmation, it does not delete")
        assertNull(ready(vm).failure)
    }

    @Test
    fun `a refused withdrawal that cannot help offers no retry`() = runTest(dispatcher) {
        val api =
            FakeEnquiryApi().apply {
                mine = listOf(AuthResult.Ok(listOf(myEnquiry("e-1"))))
                withdrawals = listOf(refused("UNEXPECTED", "error.unexpected"))
            }
        val vm = MyEnquiriesViewModel(api)
        vm.load()
        advanceUntilIdle()
        vm.askWithdraw("e-1")
        vm.confirmWithdraw()
        advanceUntilIdle()

        vm.retryWithdraw()
        assertNull(ready(vm).confirming)
    }

    @Test
    fun `a withdrawal whose list cannot be read again drops that row`() = runTest(dispatcher) {
        val api =
            FakeEnquiryApi().apply {
                mine = listOf(AuthResult.Ok(listOf(myEnquiry("e-1"), myEnquiry("e-2"))), AuthResult.TransportFailure)
            }
        val vm = MyEnquiriesViewModel(api)
        vm.load()
        advanceUntilIdle()
        vm.askWithdraw("e-2")
        vm.confirmWithdraw()
        advanceUntilIdle()

        assertEquals(listOf("e-1"), ready(vm).rows.map { it.id })
        assertTrue(ready(vm).withdrawn)
        assertFalse(ready(vm).withdrawing)
    }

    @Test
    fun `off hides entry`() = runTest(dispatcher) {
        // The list is never switched off: with none sent there is simply no entry.
        val none = MyEnquiriesViewModel(FakeEnquiryApi())
        none.load()
        advanceUntilIdle()
        assertFalse(none.state.value.showsEntry)

        val some = MyEnquiriesViewModel(FakeEnquiryApi().apply { mine = listOf(AuthResult.Ok(listOf(myEnquiry()))) })
        some.load()
        advanceUntilIdle()
        assertTrue(some.state.value.showsEntry)

        val failed = MyEnquiriesViewModel(FakeEnquiryApi().apply { mine = listOf(AuthResult.TransportFailure) })
        failed.load()
        advanceUntilIdle()
        assertEquals(MyEnquiriesUiState.Error(HUB_OFFLINE_KEY, retryable = true), failed.state.value)
        assertFalse(failed.state.value.showsEntry)
    }

    @Test
    fun `a return refreshes the owners' answers without a loader`() = runTest(dispatcher) {
        val api =
            FakeEnquiryApi().apply {
                mine =
                    listOf(
                        AuthResult.Ok(listOf(myEnquiry())),
                        AuthResult.Ok(
                            listOf(myEnquiry(status = "closed", outcome = "call_us", phone = "+8801711000000")),
                        ),
                    )
            }
        val vm = MyEnquiriesViewModel(api)
        vm.load()
        advanceUntilIdle()

        vm.load()
        assertIs<MyEnquiriesUiState.Ready>(vm.state.value, "rows stay while the answer arrives")
        advanceUntilIdle()
        assertEquals("call_us", ready(vm).rows.single().outcome)
    }

    @Test
    fun `a late re-read never closes an open withdraw confirmation`() = runTest(dispatcher) {
        val api =
            FakeEnquiryApi().apply {
                mine = listOf(AuthResult.Ok(listOf(myEnquiry("e-1"))), AuthResult.Ok(emptyList()))
            }
        val vm = MyEnquiriesViewModel(api)
        vm.load()
        advanceUntilIdle()

        // A return to the screen starts a re-read; the guardian taps Withdraw before it lands.
        vm.load()
        vm.askWithdraw("e-1")
        advanceUntilIdle()

        assertEquals("e-1", ready(vm).confirming)
        assertEquals(listOf("e-1"), ready(vm).rows.map { it.id })
    }

    @Test
    fun `a failed quiet re-read keeps the rows and says so, and the entry stays`() = runTest(dispatcher) {
        val api =
            FakeEnquiryApi().apply {
                mine =
                    listOf(
                        AuthResult.Ok(listOf(myEnquiry("e-1"))),
                        AuthResult.TransportFailure,
                        AuthResult.Ok(listOf(myEnquiry("e-1"))),
                    )
            }
        val vm = MyEnquiriesViewModel(api)
        vm.load()
        advanceUntilIdle()

        vm.load()
        advanceUntilIdle()
        assertEquals(listOf("e-1"), ready(vm).rows.map { it.id })
        assertEquals(EnquiryFailure(HUB_OFFLINE_KEY, canRetry = true), ready(vm).refreshFailure)
        assertTrue(vm.state.value.showsEntry, "More keeps its row through a dropped connection")

        vm.load()
        advanceUntilIdle()
        assertNull(ready(vm).refreshFailure)
    }

    @Test
    fun `two loads read once`() = runTest(dispatcher) {
        val api = FakeEnquiryApi()
        val vm = MyEnquiriesViewModel(api)
        vm.load()
        vm.load()
        advanceUntilIdle()
        assertEquals(1, api.calls.count { it == "GET mine" })
    }
}
