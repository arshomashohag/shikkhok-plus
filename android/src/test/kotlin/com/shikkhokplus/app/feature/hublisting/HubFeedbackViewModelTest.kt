package com.shikkhokplus.app.feature.hublisting

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.feature.auth.AuthResult
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
import kotlin.test.assertNull

/** "Did the hub bring you a student?": the highlighted reply is only one the server accepted. */
@OptIn(ExperimentalCoroutinesApi::class)
class HubFeedbackViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    /** Records each send and answers with the next queued result. */
    private class FakeFeedbackApi : HubFeedbackApi {
        val sent = mutableListOf<Triple<String, Int, FeedbackAnswer>>()
        var result: AuthResult<Unit> = AuthResult.Ok(Unit)

        override suspend fun answer(ownerId: String, day: Int, answer: FeedbackAnswer): AuthResult<Unit> {
            sent += Triple(ownerId, day, answer)
            return result
        }
    }

    @Test
    fun an_answer_is_sent_for_the_items_owner_and_day_and_overwrites() = runTest(dispatcher) {
        val api = FakeFeedbackApi()
        val vm = HubFeedbackViewModel(api, ownerId = "o-1", day = 90)

        vm.answer(FeedbackAnswer.NOT_YET)
        advanceUntilIdle()
        vm.answer(FeedbackAnswer.YES)
        advanceUntilIdle()

        assertEquals(
            listOf(Triple("o-1", 90, FeedbackAnswer.NOT_YET), Triple("o-1", 90, FeedbackAnswer.YES)),
            api.sent,
        )
        assertEquals(FeedbackAnswer.YES, vm.state.value.saved)
        assertNull(vm.state.value.failure)
    }

    @Test
    fun a_failed_send_keeps_the_saved_answer_and_retry_sends_the_wanted_one() = runTest(dispatcher) {
        val api = FakeFeedbackApi()
        val vm = HubFeedbackViewModel(api, ownerId = "o-1", day = 60)
        vm.answer(FeedbackAnswer.NOT_SURE)
        advanceUntilIdle()

        api.result = AuthResult.TransportFailure
        vm.answer(FeedbackAnswer.YES)
        advanceUntilIdle()

        assertEquals(FeedbackAnswer.NOT_SURE, vm.state.value.saved)
        assertEquals(HUB_OFFLINE_KEY, vm.state.value.failure?.messageKey)

        api.result = AuthResult.Ok(Unit)
        vm.retry()
        advanceUntilIdle()

        assertEquals(FeedbackAnswer.YES, api.sent.last().third)
        assertEquals(FeedbackAnswer.YES, vm.state.value.saved)
        assertNull(vm.state.value.failure)
    }

    @Test
    fun a_question_never_asked_is_shown_and_not_retried() = runTest(dispatcher) {
        val api = FakeFeedbackApi()
        api.result =
            AuthResult.Refused(
                ErrorEnvelope(
                    ErrorBody("HUB_FEEDBACK_NOT_ASKED", retryable = false, messageKey = "hub.feedback_not_asked"),
                ),
            )
        val vm = HubFeedbackViewModel(api, ownerId = "o-1", day = 60)

        vm.answer(FeedbackAnswer.YES)
        advanceUntilIdle()
        vm.retry()
        advanceUntilIdle()

        assertEquals("hub.feedback_not_asked", vm.state.value.failure?.messageKey)
        assertEquals(1, api.sent.size)
        assertNull(vm.state.value.saved)
    }
}
