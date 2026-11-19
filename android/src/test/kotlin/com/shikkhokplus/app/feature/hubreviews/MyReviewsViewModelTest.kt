package com.shikkhokplus.app.feature.hubreviews

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
import kotlin.test.assertTrue

/**
 * The guardian's reviewable list, and whether the guardian home offers it.
 *
 * The entry is drawn only while the server lists at least one batch:
 * with reviews switched off the list holds only what was already
 * reviewed, so a guardian who never wrote one sees no entry at all.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class MyReviewsViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val row =
        ReviewableBatch(
            batchId = "b-1",
            batchTitle = "Physics 9",
            ownerPublicName = "Rahima",
            state = "not_yet",
            eligibleFrom = "2026-12-01",
        )

    @Test
    fun `the list is the server's rows, in its order`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply { reviewable = listOf(AuthResult.Ok(listOf(row))) }
        val vm = MyReviewsViewModel(api)
        assertEquals(MyReviewsUiState.Loading, vm.state.value)

        vm.load()
        advanceUntilIdle()

        val ready = assertIs<MyReviewsUiState.Ready>(vm.state.value)
        assertEquals(listOf(row), ready.rows)
        assertTrue(ready.showsEntry)
        assertEquals(ReviewableState.NOT_YET, ReviewableState.fromWire(row.state))
        assertEquals(null, ReviewableState.fromWire("future"))
    }

    @Test
    fun `off hides entry`() = runTest(dispatcher) {
        // Switched off, the server lists only reviews already written: none here.
        val empty = MyReviewsViewModel(FakeReviewsApi().apply { reviewable = listOf(AuthResult.Ok(emptyList())) })
        empty.load()
        advanceUntilIdle()
        assertFalse(empty.state.value.showsEntry)

        val off = MyReviewsViewModel(FakeReviewsApi().apply { reviewable = listOf(reviewsOff) })
        off.load()
        advanceUntilIdle()
        assertEquals(MyReviewsUiState.Off, off.state.value)
        assertFalse(off.state.value.showsEntry)
    }

    @Test
    fun `a failed read hides the entry and the list offers retry`() = runTest(dispatcher) {
        val api =
            FakeReviewsApi().apply {
                reviewable = listOf(AuthResult.TransportFailure, AuthResult.Ok(listOf(row)))
            }
        val vm = MyReviewsViewModel(api)
        vm.load()
        advanceUntilIdle()

        assertEquals(MyReviewsUiState.Error(HUB_OFFLINE_KEY, retryable = true), vm.state.value)
        assertFalse(vm.state.value.showsEntry)

        vm.load()
        advanceUntilIdle()
        assertTrue(vm.state.value.showsEntry)
    }

    @Test
    fun `a reload keeps the rows on screen until the answer arrives`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply { reviewable = listOf(AuthResult.Ok(listOf(row))) }
        val vm = MyReviewsViewModel(api)
        vm.load()
        advanceUntilIdle()

        vm.load()

        assertIs<MyReviewsUiState.Ready>(vm.state.value)
    }
}
