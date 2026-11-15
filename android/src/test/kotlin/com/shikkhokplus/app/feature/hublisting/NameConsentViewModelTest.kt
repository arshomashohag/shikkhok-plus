package com.shikkhokplus.app.feature.hublisting

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
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** "Show my name on the centre's page": one server-held choice per membership. */
@OptIn(ExperimentalCoroutinesApi::class)
class NameConsentViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun membership(consent: Boolean = false) =
        CentreMembership("m-1", "c-1", "Udayan", role = "teacher", publicNameConsent = consent)

    private suspend fun loaded(fake: FakeHubApi): NameConsentViewModel {
        val vm = NameConsentViewModel(fake)
        vm.load()
        dispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    @Test
    fun the_rows_are_the_servers_memberships_and_current_choices() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.memberships = AuthResult.Ok(listOf(membership(consent = true)))
        val vm = loaded(fake)

        val body = assertIs<NameConsentBody.Loaded>(vm.state.value.body)
        assertTrue(body.rows.single().membership.publicNameConsent)
    }

    @Test
    fun a_toggle_sends_the_flag_and_shows_the_servers_answer() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.memberships = AuthResult.Ok(listOf(membership(consent = false)))
        val vm = loaded(fake)

        vm.set("c-1", true)
        advanceUntilIdle()

        assertEquals(listOf("c-1" to true), fake.consents)
        val row = assertIs<NameConsentBody.Loaded>(vm.state.value.body).rows.single()
        assertTrue(row.membership.publicNameConsent)
        assertNull(row.failureKey)
    }

    @Test
    fun a_failed_write_leaves_the_box_as_it_was_and_retry_sends_the_wanted_value() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.memberships = AuthResult.Ok(listOf(membership(consent = false)))
        val vm = loaded(fake)
        fake.consentResult = AuthResult.TransportFailure

        vm.set("c-1", true)
        advanceUntilIdle()

        val row = assertIs<NameConsentBody.Loaded>(vm.state.value.body).rows.single()
        assertFalse(row.membership.publicNameConsent, "the box stays at what the server last said")
        assertEquals("error.network.unreachable", row.failureKey)

        fake.consentResult = AuthResult.Ok(Unit)
        vm.retry("c-1")
        advanceUntilIdle()
        assertEquals(listOf("c-1" to true, "c-1" to true), fake.consents)
        assertTrue(assertIs<NameConsentBody.Loaded>(vm.state.value.body).rows.single().membership.publicNameConsent)
    }

    @Test
    fun a_failed_read_offers_retry() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.memberships = AuthResult.TransportFailure
        val vm = loaded(fake)
        assertTrue(assertIs<NameConsentBody.Failed>(vm.state.value.body).retryable)

        fake.memberships = AuthResult.Ok(emptyList())
        vm.retryLoad()
        advanceUntilIdle()
        assertEquals(emptyList(), assertIs<NameConsentBody.Loaded>(vm.state.value.body).rows)
    }

    @Test
    fun reentering_the_screen_keeps_a_failed_toggle_and_its_retry() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.memberships = AuthResult.Ok(listOf(membership(consent = false)))
        val vm = loaded(fake)
        fake.consentResult = AuthResult.TransportFailure
        vm.set("c-1", true)
        advanceUntilIdle()

        vm.load()
        advanceUntilIdle()

        val row = assertIs<NameConsentBody.Loaded>(vm.state.value.body).rows.single()
        assertEquals("error.network.unreachable", row.failureKey)
    }
}
