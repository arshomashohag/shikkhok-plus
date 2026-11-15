package com.shikkhokplus.app.feature.hublisting

import com.shikkhokplus.app.core.model.Money
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
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** The batch listings list and its editor. */
@OptIn(ExperimentalCoroutinesApi::class)
class BatchListingsViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun refusal(key: String) = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, key)))

    @Test
    fun the_list_carries_the_servers_fee_string_and_teacher_names() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.batches =
            AuthResult.Ok(
                listOf(
                    batchListing(fee = Money.of("1500.00"), teacherNames = listOf("Rahima", "Centre faculty")),
                    batchListing(id = "b-2", fee = null),
                ),
            )
        val vm = BatchListingsViewModel(fake)
        vm.load()
        advanceUntilIdle()

        val loaded = assertIs<BatchListingsBody.Loaded>(vm.state.value.body)
        assertEquals("1500.00", loaded.batches[0].fee.toString())
        assertNull(loaded.batches[1].fee, "a fee the owner did not show is absent")
    }

    @Test
    fun a_failed_read_is_an_error_with_retry() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.batches = AuthResult.TransportFailure
        val vm = BatchListingsViewModel(fake)
        vm.load()
        advanceUntilIdle()
        assertTrue(assertIs<BatchListingsBody.Failed>(vm.state.value.body).retryable)

        fake.batches = AuthResult.Ok(emptyList())
        vm.retry()
        advanceUntilIdle()
        assertEquals(emptyList(), assertIs<BatchListingsBody.Loaded>(vm.state.value.body).batches)
    }

    @Test
    fun the_first_save_always_carries_both_visibility_flags() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.batches = AuthResult.Ok(listOf(batchListing()))
        val vm = BatchListingsViewModel(fake)
        vm.load()
        advanceUntilIdle()

        vm.edit("b-1")
        vm.change {
            it.copy(descriptionEn = "Weekly physics", levels = "9, 10 ,", tags = "mechanics،optics", mode = "online")
        }
        vm.save()
        advanceUntilIdle()

        val (id, body) = fake.batchSaved.single()
        assertEquals("b-1", id)
        assertEquals(false, body.showFee)
        assertEquals(false, body.showSchedule)
        assertEquals(listOf("9", "10"), body.classLevels)
        assertEquals(listOf("mechanics", "optics"), body.subjectTags)
        assertEquals("online", body.mode)
        assertEquals("open", body.admissions)
    }

    @Test
    fun a_failed_save_keeps_the_form_and_retry_repeats_it() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.batches = AuthResult.Ok(listOf(batchListing()))
        val vm = BatchListingsViewModel(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit("b-1")
        vm.change { it.copy(descriptionBn = "বিবরণ") }
        fake.batchSave = AuthResult.TransportFailure

        vm.save()
        advanceUntilIdle()

        val editor = assertNotNull(vm.state.value.editor)
        assertEquals("error.network.unreachable", editor.failure?.messageKey)
        assertEquals("বিবরণ", editor.draft.descriptionBn)

        fake.batchSave = AuthResult.Ok(batchListing(publishable = true))
        vm.retry()
        advanceUntilIdle()
        assertEquals(2, fake.batchSaved.size)
        assertEquals(fake.batchSaved[0], fake.batchSaved[1])
        assertNull(vm.state.value.editor?.failure)
        assertTrue(vm.state.value.editor!!.canPublish, "the server's publishable, with nothing unsaved")
    }

    @Test
    fun publish_follows_the_servers_publishable_and_a_suspended_batch_is_read_only() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.batches =
            AuthResult.Ok(
                listOf(
                    batchListing(id = "b-1", publishable = false),
                    batchListing(id = "b-2", publishable = true),
                    batchListing(id = "b-3", status = "suspended", publishable = true),
                ),
            )
        val vm = BatchListingsViewModel(fake)
        vm.load()
        advanceUntilIdle()

        vm.edit("b-1")
        assertFalse(vm.state.value.editor!!.canPublish)
        vm.publish()
        advanceUntilIdle()
        assertTrue(fake.batchPublished.isEmpty())

        vm.edit("b-3")
        assertTrue(vm.state.value.editor!!.readOnly)
        assertFalse(vm.state.value.editor!!.canPublish)
        vm.save()
        advanceUntilIdle()
        assertTrue(fake.batchSaved.isEmpty())

        vm.edit("b-2")
        vm.publish()
        advanceUntilIdle()
        assertEquals(listOf("b-2"), fake.batchPublished)
        assertEquals("published", vm.state.value.editor!!.batch.status)
    }

    @Test
    fun unpublish_and_a_refusal_name_the_servers_key() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.batches = AuthResult.Ok(listOf(batchListing(status = "published", publishable = true)))
        val vm = BatchListingsViewModel(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit("b-1")

        fake.batchUnpublish = refusal("hub.batch_inactive")
        vm.unpublish()
        advanceUntilIdle()
        assertEquals("hub.batch_inactive", vm.state.value.editor?.failure?.messageKey)
        assertFalse(vm.state.value.editor!!.failure!!.canRetry, "the server said repeating cannot help")

        fake.batchUnpublish = null
        vm.unpublish()
        advanceUntilIdle()
        assertEquals("hidden", vm.state.value.editor?.batch?.status)
    }

    @Test
    fun closing_the_editor_reloads_the_list() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.batches = AuthResult.Ok(listOf(batchListing()))
        val vm = BatchListingsViewModel(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit("b-1")
        fake.batches = AuthResult.Ok(listOf(batchListing(status = "published")))

        vm.close()
        advanceUntilIdle()

        assertNull(vm.state.value.editor)
        assertEquals("published", assertIs<BatchListingsBody.Loaded>(vm.state.value.body).batches.single().status)
    }

    @Test
    fun the_servers_fallback_name_is_localized_for_display_only() {
        assertEquals("সেন্টারের শিক্ষকবৃন্দ", teacherLine(listOf("Centre faculty"), "সেন্টারের শিক্ষকবৃন্দ"))
        assertEquals("Karim", teacherLine(listOf("Karim"), "সেন্টারের শিক্ষকবৃন্দ"))
    }
}
