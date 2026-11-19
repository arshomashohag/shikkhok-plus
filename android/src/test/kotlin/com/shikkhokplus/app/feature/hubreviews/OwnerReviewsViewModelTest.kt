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
 * The owner's Reviews screen: ratings exactly as the public sees them,
 * and a reply per review that is checked before it appears.
 *
 * **Below three published reviews a batch's figures arrive as nulls** and
 * the row is neutral, drawn from those nulls and never from a count kept
 * here [T2-a]. The average is the server's `average_label`, shown as sent
 * [F13].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class OwnerReviewsViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val rated =
        OwnerBatchRating(
            batchId = "b-1",
            batchTitle = "Physics 9",
            reviewCount = 3,
            averageLabel = "4.3",
            distribution = listOf(0, 0, 0, 2, 1),
        )
    private val quiet = OwnerBatchRating(batchId = "b-2", batchTitle = "Chemistry 10")

    private fun page(vararg reviews: OwnerReview) =
        AuthResult.Ok(OwnerReviewsResponse(listOf(rated, quiet), reviews.toList()))

    private fun TestScope.opened(api: FakeReviewsApi): OwnerReviewsViewModel {
        val vm = OwnerReviewsViewModel(api)
        vm.load()
        advanceUntilIdle()
        return vm
    }

    private fun OwnerReviewsViewModel.content(): OwnerReviewsContent =
        assertIs<OwnerReviewsUiState.Ready>(state.value).content

    @Test
    fun `off hides entry`() = runTest(dispatcher) {
        val vm = opened(FakeReviewsApi().apply { owner = listOf(reviewsOff) })

        assertEquals(OwnerReviewsUiState.Off, vm.state.value)
        assertFalse(vm.state.value.showsEntry)

        val failed = opened(FakeReviewsApi().apply { owner = listOf(AuthResult.TransportFailure) })
        assertEquals(OwnerReviewsUiState.Error(HUB_OFFLINE_KEY, retryable = true), failed.state.value)
        assertFalse(failed.state.value.showsEntry, "only a read that succeeded draws the entry")

        val read = opened(FakeReviewsApi().apply { owner = listOf(page()) })
        assertTrue(read.state.value.showsEntry)
    }

    @Test
    fun `the rating row is the server's label, and neutral from its nulls`() = runTest(dispatcher) {
        val vm = opened(FakeReviewsApi().apply { owner = listOf(page(ownerReview())) })

        val content = vm.content()
        assertEquals(RatingLine.Shown("4.3", 3, listOf(0, 0, 0, 2, 1)), content.batches[0].ratingLine())
        assertEquals(RatingLine.BelowThreshold, content.batches[1].ratingLine())
        // A count alone, with no label, still reads as neutral: the label decides.
        assertEquals(RatingLine.BelowThreshold, quiet.copy(reviewCount = 2).ratingLine())
        assertEquals("Physics 9", content.titleOf("b-1"))
        assertEquals("Patient with questions", content.cards.single().review.body)
    }

    @Test
    fun `a reply is sent and then awaits review`() = runTest(dispatcher) {
        val api =
            FakeReviewsApi().apply {
                owner = listOf(page(ownerReview()))
                replies = listOf(AuthResult.Ok(ownerReview(myReplyStatus = "pending", myReplyBody = "Thank you")))
            }
        val vm = opened(api)

        vm.editReply("r-1", "  Thank you  ")
        vm.sendReply("r-1")
        assertIs<OwnerReviewsUiState.Saving>(vm.state.value)
        advanceUntilIdle()

        assertEquals("PUT reply r-1 Thank you", api.calls.last())
        val card = vm.content().cards.single()
        assertEquals("pending", card.review.myReplyStatus)
        assertEquals(ReviewStatusWords.AWAITING, statusWords("pending"))
        assertEquals("Thank you", card.draft)
        assertNull(card.failure)
    }

    @Test
    fun `a blank reply is not sent`() = runTest(dispatcher) {
        val api = FakeReviewsApi().apply { owner = listOf(page(ownerReview())) }
        val vm = opened(api)

        vm.editReply("r-1", "   ")
        vm.sendReply("r-1")
        advanceUntilIdle()

        assertEquals(listOf("GET owner"), api.calls)
    }

    @Test
    fun `network failure keeps text and offers retry`() = runTest(dispatcher) {
        val api =
            FakeReviewsApi().apply {
                owner = listOf(page(ownerReview()))
                replies =
                    listOf(
                        AuthResult.TransportFailure,
                        AuthResult.Ok(ownerReview(myReplyStatus = "pending", myReplyBody = "Thanks a lot")),
                    )
            }
        val vm = opened(api)
        vm.editReply("r-1", "Thanks")
        vm.sendReply("r-1")
        advanceUntilIdle()

        val failed = vm.content().cards.single()
        assertEquals(HUB_OFFLINE_KEY, failed.failure?.messageKey)
        assertTrue(failed.failure?.canRetry == true)
        assertEquals("Thanks", failed.draft)

        vm.editReply("r-1", "Thanks a lot")
        vm.retry("r-1")
        advanceUntilIdle()

        assertEquals("PUT reply r-1 Thanks a lot", api.calls.last())
        assertNull(vm.content().cards.single().failure)
    }

    @Test
    fun `contact refused keeps text`() = runTest(dispatcher) {
        val api =
            FakeReviewsApi().apply {
                owner = listOf(page(ownerReview()))
                replies = listOf(refused("REVIEW_CONTAINS_CONTACT", "hub.review.contains_contact"))
            }
        val vm = opened(api)
        vm.editReply("r-1", "See www.example.com")
        vm.sendReply("r-1")
        advanceUntilIdle()

        val card = vm.content().cards.single()
        assertEquals("hub.review.contains_contact", card.failure?.messageKey)
        assertFalse(card.failure?.canRetry ?: true)
        assertEquals("See www.example.com", card.draft)
    }

    @Test
    fun `delete confirmed`() = runTest(dispatcher) {
        val replied = ownerReview(myReplyStatus = "held", myReplyBody = "Thank you")
        val api = FakeReviewsApi().apply { owner = listOf(page(replied)) }
        val vm = opened(api)
        // A held reply reads to its author as awaiting review [T11-c].
        assertEquals(ReviewStatusWords.AWAITING, statusWords("held"))
        assertEquals("Thank you", vm.content().cards.single().draft)

        vm.confirmDeleteReply("r-1")
        advanceUntilIdle()
        assertEquals(listOf("GET owner"), api.calls, "nothing is deleted without the confirmation")

        vm.askDeleteReply("r-1")
        vm.cancelDeleteReply("r-1")
        assertFalse(vm.content().cards.single().confirmingDelete)

        vm.askDeleteReply("r-1")
        vm.confirmDeleteReply("r-1")
        advanceUntilIdle()

        assertEquals("DELETE reply r-1", api.calls.last())
        val content = vm.content()
        val card = content.cards.single()
        assertNull(card.review.myReplyStatus)
        assertNull(card.review.myReplyBody)
        assertNull(card.review.replyBody)
        assertEquals("", card.draft)
        assertTrue(content.replyDeleted)
        vm.dismissNotice()
        assertFalse(vm.content().replyDeleted)
    }

    @Test
    fun `a failed delete keeps the reply and retry asks again`() = runTest(dispatcher) {
        val api =
            FakeReviewsApi().apply {
                owner = listOf(page(ownerReview(myReplyStatus = "pending", myReplyBody = "Thank you")))
                replyDeletes = listOf(AuthResult.TransportFailure)
            }
        val vm = opened(api)
        vm.askDeleteReply("r-1")
        vm.confirmDeleteReply("r-1")
        advanceUntilIdle()

        val card = vm.content().cards.single()
        assertEquals(WriteKind.DELETE, card.failure?.kind)
        assertEquals("pending", card.review.myReplyStatus)

        vm.retry("r-1")
        assertTrue(vm.content().cards.single().confirmingDelete)
        assertEquals(1, api.calls.count { it.startsWith("DELETE") })
    }

    @Test
    fun `status and reason words come from tables, never a raw code`() {
        assertEquals(ReviewStatusWords.APPROVED, statusWords("approved"))
        assertEquals(ReviewStatusWords.PUBLISHED, statusWords("published"))
        assertEquals(ReviewStatusWords.NOT_PUBLISHED, statusWords("rejected"))
        assertEquals(ReviewStatusWords.NOT_PUBLISHED, statusWords("removed"))
        assertNull(statusWords("future"))
        assertEquals(ReviewReason.PERSONAL_INFO, ReviewReason.fromWire("personal_info"))
        assertEquals(ReviewReason.OTHER, ReviewReason.fromWire("new_code"))
        assertEquals(ReviewReason.OTHER, ReviewReason.fromWire(null))
        assertEquals(Tenure.GT_1Y, Tenure.fromWire("gt_1y"))
        assertNull(Tenure.fromWire("2y"))
    }
}
