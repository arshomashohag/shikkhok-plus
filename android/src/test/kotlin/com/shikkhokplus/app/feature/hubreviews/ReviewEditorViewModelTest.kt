package com.shikkhokplus.app.feature.hubreviews

import com.shikkhokplus.app.feature.auth.AuthResult
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
 * One batch's review, as its guardian author writes, edits and deletes it.
 *
 * **The server decides; the view model carries.** Whether the form is
 * writable is `can_write`, why a member cannot write yet is `standing`,
 * and a refusal is the server's message key; a failed write keeps the
 * rating and the words and offers Retry only when trying again can help
 * [TC-8].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ReviewEditorViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun TestScope.opened(api: FakeReviewsApi): ReviewEditorViewModel {
        val vm = ReviewEditorViewModel(api, BATCH)
        vm.load()
        advanceUntilIdle()
        return vm
    }

    private fun ReviewEditorViewModel.form(): ReviewForm = assertIs<ReviewEditorUiState.Ready>(state.value).form

    @Test
    fun `submit success`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply {
            reads = listOf(AuthResult.Ok(eligible))
            saves = listOf(AuthResult.Ok(mine(rating = 5, body = "Clear teaching")))
        }
        val vm = opened(api)
        assertNull(vm.form().review.review)

        vm.pickRating(5)
        vm.editText("  Clear teaching  ")
        vm.save()
        assertIs<ReviewEditorUiState.Saving>(vm.state.value)
        advanceUntilIdle()

        // The words go stripped, and the screen draws the server's answer.
        assertEquals(listOf("GET $BATCH", "PUT $BATCH 5 Clear teaching"), api.calls)
        val form = vm.form()
        assertEquals("pending", form.review.review?.status)
        assertEquals(ReviewStatusWords.AWAITING, statusWords(form.review.review!!.status))
        assertNull(form.failure)
    }

    @Test
    fun `an empty body is sent as none and nothing is sent without a rating`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply {
            reads = listOf(AuthResult.Ok(eligible))
            saves = listOf(AuthResult.Ok(mine(body = null)))
        }
        val vm = opened(api)

        vm.editText("   ")
        vm.save()
        advanceUntilIdle()
        assertEquals(listOf("GET $BATCH"), api.calls, "no rating, no request")

        vm.pickRating(3)
        vm.save()
        advanceUntilIdle()
        assertEquals("PUT $BATCH 3 null", api.calls.last())
    }

    @Test
    fun `not yet eligible renders reason and date`() = runTest(dispatcher) {
        val waiting =
            MyReviewResponse(
                standing = "not_yet",
                waitingOn = "tenure",
                eligibleFrom = "2026-12-01",
                canWrite = false,
            )
        val api = FakeReviewsApi().apply { reads = listOf(AuthResult.Ok(waiting)) }
        val vm = opened(api)

        val form = vm.form()
        assertEquals(StandingNote("hub.review.not_yet_eligible", "2026-12-01"), form.note)
        assertFalse(form.review.canWrite)

        // A typed rating is not taken while the server says no.
        vm.pickRating(4)
        vm.save()
        advanceUntilIdle()
        assertNull(vm.form().rating)
        assertEquals(listOf("GET $BATCH"), api.calls)

        val attendance = waiting.copy(waitingOn = "attendance", eligibleFrom = null)
        assertEquals(StandingNote("hub.review.needs_attendance", null), attendance.standingNote())
        val closed = MyReviewResponse(standing = "closed", canWrite = false)
        assertEquals(StandingNote("hub.review.window_closed", null), closed.standingNote())
        // An author is told nothing about standing: can_write says it.
        assertNull(mine().copy(standing = "not_yet").standingNote())
    }

    @Test
    fun `a refused write names its day when the server sends one`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply {
            reads = listOf(AuthResult.Ok(eligible))
            saves =
                listOf(
                    refused(
                        "REVIEW_NOT_YET_ELIGIBLE",
                        "hub.review.not_yet_eligible",
                        details = mapOf("eligible_from" to "2026-12-02"),
                    ),
                )
        }
        val vm = opened(api)
        vm.pickRating(2)
        vm.save()
        advanceUntilIdle()

        val failure = vm.form().failure
        assertEquals("hub.review.not_yet_eligible", failure?.messageKey)
        assertEquals("2026-12-02", failure?.eligibleFrom)
        assertFalse(failure?.canRetry ?: true)
    }

    @Test
    fun `edit closed is read only`() = runTest(dispatcher) {
        val closed = mine(status = "published", canWrite = false, editUntil = null, reply = "Thank you")
        val api = FakeReviewsApi().apply { reads = listOf(AuthResult.Ok(closed)) }
        val vm = opened(api)

        vm.pickRating(1)
        vm.editText("changed")
        vm.save()
        advanceUntilIdle()

        val form = vm.form()
        assertFalse(form.review.canWrite)
        assertFalse(form.canSave)
        assertEquals(4, form.rating, "the review's own rating, unchanged")
        assertEquals("Clear teaching", form.text)
        assertEquals("Thank you", form.review.review?.replyBody)
        assertEquals(listOf("GET $BATCH"), api.calls)

        // Delete is never gated by the window.
        vm.askDelete()
        assertTrue(vm.form().confirmingDelete)
    }

    @Test
    fun `delete confirmed`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply {
            reads = listOf(AuthResult.Ok(mine()), AuthResult.Ok(eligible))
        }
        val vm = opened(api)

        vm.confirmDelete()
        advanceUntilIdle()
        assertEquals(listOf("GET $BATCH"), api.calls, "nothing is deleted without the confirmation")

        vm.askDelete()
        vm.cancelDelete()
        assertFalse(vm.form().confirmingDelete)

        vm.askDelete()
        vm.confirmDelete()
        advanceUntilIdle()

        assertEquals(listOf("GET $BATCH", "DELETE $BATCH", "GET $BATCH"), api.calls)
        val form = vm.form()
        assertNull(form.review.review)
        assertTrue(form.deleted)
        assertNull(form.rating)
        assertEquals("", form.text)
        vm.dismissNotice()
        assertFalse(vm.form().deleted)
    }

    @Test
    fun `after a delete an unreadable state offers nothing writable`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply {
            reads = listOf(AuthResult.Ok(mine()), AuthResult.TransportFailure)
        }
        val vm = opened(api)
        vm.askDelete()
        vm.confirmDelete()
        advanceUntilIdle()

        val form = vm.form()
        assertNull(form.review.review)
        assertFalse(form.review.canWrite)
        assertNull(form.review.editUntil)
        assertTrue(form.deleted)
    }

    @Test
    fun `contact refused keeps text`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply {
            reads = listOf(AuthResult.Ok(eligible))
            saves =
                listOf(
                    refused(
                        "REVIEW_CONTAINS_CONTACT",
                        "hub.review.contains_contact",
                        details = mapOf("field" to "body"),
                    ),
                )
        }
        val vm = opened(api)
        vm.pickRating(5)
        vm.editText("Call 01712345678")
        vm.save()
        advanceUntilIdle()

        val form = vm.form()
        assertEquals("hub.review.contains_contact", form.failure?.messageKey)
        assertEquals(WriteKind.SAVE, form.failure?.kind)
        assertFalse(form.failure?.canRetry ?: true)
        assertEquals(5, form.rating)
        assertEquals("Call 01712345678", form.text)

        vm.retry()
        advanceUntilIdle()
        assertEquals(1, api.calls.count { it.startsWith("PUT") }, "a refusal is not retried")
    }

    @Test
    fun `network failure keeps text and offers retry`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply {
            reads = listOf(AuthResult.Ok(eligible))
            saves = listOf(AuthResult.TransportFailure, AuthResult.Ok(mine(rating = 3, body = "Good, then better")))
        }
        val vm = opened(api)
        vm.pickRating(3)
        vm.editText("Good")
        vm.save()
        advanceUntilIdle()

        val failed = vm.form()
        assertEquals(HUB_OFFLINE_KEY, failed.failure?.messageKey)
        assertTrue(failed.failure?.canRetry == true)
        assertEquals("Good", failed.text)
        assertEquals(3, failed.rating)

        // Retry sends what is on screen when it is pressed.
        vm.editText("Good, then better")
        vm.retry()
        advanceUntilIdle()

        assertEquals("PUT $BATCH 3 Good, then better", api.calls.last())
        assertNull(vm.form().failure)
    }

    @Test
    fun `a failed delete keeps the review and retry asks again`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply {
            reads = listOf(AuthResult.Ok(mine()))
            deletes = listOf(AuthResult.TransportFailure)
        }
        val vm = opened(api)
        vm.askDelete()
        vm.confirmDelete()
        advanceUntilIdle()

        val form = vm.form()
        assertEquals(WriteKind.DELETE, form.failure?.kind)
        assertEquals(4, form.review.review?.rating)

        vm.retry()
        assertTrue(vm.form().confirmingDelete, "Retry re-opens the confirmation; it never deletes unasked")
        assertEquals(1, api.calls.count { it.startsWith("DELETE") })
    }

    @Test
    fun `a failed read offers retry when the server says it can help`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply {
            reads = listOf(AuthResult.TransportFailure, AuthResult.Ok(eligible))
        }
        val vm = opened(api)
        assertEquals(ReviewEditorUiState.Error(HUB_OFFLINE_KEY, retryable = true), vm.state.value)

        vm.retryLoad()
        advanceUntilIdle()
        assertIs<ReviewEditorUiState.Ready>(vm.state.value)

        val off = FakeReviewsApi().apply { reads = listOf(reviewsOff) }
        assertEquals(ReviewEditorUiState.Off, opened(off).state.value)
    }

    @Test
    fun `the words stop at the server's limit`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply { reads = listOf(AuthResult.Ok(eligible)) }
        val vm = opened(api)

        vm.editText("x".repeat(REVIEW_TEXT_MAX + 5))

        assertEquals(REVIEW_TEXT_MAX, vm.form().text.length)
    }

    private companion object {
        const val BATCH = "b-1"
    }
}
