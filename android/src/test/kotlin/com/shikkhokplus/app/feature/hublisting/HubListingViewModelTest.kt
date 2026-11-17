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
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** The owner's listing editor: its state machine and what it sends. */
@OptIn(ExperimentalCoroutinesApi::class)
class HubListingViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun refusal(key: String) = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, key)))

    private fun model(fake: FakeHubApi): HubListingViewModel = HubListingViewModel(fake)

    @Test
    fun loading_then_editing_maps_checklist() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing =
            AuthResult.Ok(
                owner(
                    checklist = listOf(HubChecklistItem("public_name", true), HubChecklistItem("slug", false)),
                    publishable = false,
                ),
            )
        val vm = model(fake)
        assertIs<HubListingUiState.Loading>(vm.state.value.body)

        vm.load()
        advanceUntilIdle()

        val editing = assertIs<HubListingUiState.Editing>(vm.state.value.body)
        assertEquals(listOf(HubChecklistItem("public_name", true), HubChecklistItem("slug", false)), editing.checklist)
        assertFalse(editing.publishable)
        assertEquals("Rahima", vm.state.value.draft.publicName)
        assertFalse(vm.state.value.canPublish, "the server said it is not publishable")
    }

    @Test
    fun the_mapper_is_pure_and_publishable_is_the_servers() {
        val ready = owner(publishable = true).toUiState()
        assertTrue(assertIs<HubListingUiState.Editing>(ready).publishable)
    }

    @Test
    fun suspended_status_maps_to_read_only_state() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(status = "suspended", publishable = true))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()

        assertIs<HubListingUiState.Suspended>(vm.state.value.body)
        assertFalse(vm.state.value.canSave)
        assertFalse(vm.state.value.canPublish, "a suspended listing is never published from here")

        vm.edit { it.copy(headlineEn = "typed") }
        vm.save()
        vm.openPublish()
        advanceUntilIdle()
        assertTrue(fake.saved.isEmpty(), "nothing is sent for a suspended listing")
        assertFalse(vm.state.value.publishing)
    }

    @Test
    fun failed_save_exposes_retry_and_keeps_input() = runTest(dispatcher) {
        val fake = FakeHubApi()
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit { it.copy(headlineEn = "Physics tutor", bioBn = "পরিচিতি") }

        fake.saveResult = AuthResult.TransportFailure
        vm.save()
        advanceUntilIdle()

        val failure = assertNotNull(vm.state.value.failure)
        assertEquals("error.network.unreachable", failure.messageKey)
        assertTrue(failure.canRetry)
        assertEquals("Physics tutor", vm.state.value.draft.headlineEn, "nothing typed is lost")
        assertEquals("পরিচিতি", vm.state.value.draft.bioBn)
        assertFalse(vm.state.value.saving)

        fake.saveResult = AuthResult.Ok(owner(headlineEn = "Physics tutor", bioBn = "পরিচিতি"))
        vm.retry()
        advanceUntilIdle()

        assertEquals(2, fake.saved.size)
        assertEquals(fake.saved[0], fake.saved[1], "retry sends the same changes")
        assertEquals("Physics tutor", fake.saved[1].headlineEn)
        assertNull(fake.saved[1].publicName, "unchanged fields are omitted")
        assertNull(vm.state.value.failure)
        assertEquals(HubNotice.SAVED, vm.state.value.notice)
    }

    @Test
    fun a_refused_save_names_the_servers_message_key_and_keeps_input() = runTest(dispatcher) {
        val fake = FakeHubApi()
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit { it.copy(slug = "taken-one") }
        fake.saveResult = refusal("hub.slug_taken")

        vm.save()
        advanceUntilIdle()

        assertEquals("hub.slug_taken", vm.state.value.failure?.messageKey)
        assertEquals("taken-one", vm.state.value.draft.slug)
    }

    @Test
    fun publish_sends_server_consent_version() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(publishable = true, consentVersionCurrent = "2026-11-14"))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        assertTrue(vm.state.value.canPublish)

        vm.openPublish()
        assertTrue(vm.state.value.publishing)
        vm.publish()
        advanceUntilIdle()
        assertTrue(fake.published.isEmpty(), "Publish waits for the checkbox")

        vm.agree(true)
        vm.publish()
        advanceUntilIdle()

        assertEquals(listOf("2026-11-14"), fake.published)
        assertFalse(vm.state.value.publishing)
        assertEquals(HubNotice.PUBLISHED, vm.state.value.notice)
        assertIs<HubListingUiState.Editing>(vm.state.value.body)
    }

    @Test
    fun publish_is_not_offered_with_unsaved_edits_or_when_already_published() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(publishable = true))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit { it.copy(headlineEn = "new") }
        assertFalse(vm.state.value.canPublish, "save first")
        vm.openPublish()
        assertFalse(vm.state.value.publishing)

        fake.listing = AuthResult.Ok(owner(status = "published", publishable = true))
        val published = model(fake)
        published.load()
        advanceUntilIdle()
        assertFalse(published.state.value.canPublish)
        assertTrue(published.state.value.canUnpublish)
    }

    @Test
    fun a_failed_publish_keeps_the_sheet_and_retries() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(publishable = true))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.openPublish()
        vm.agree(true)
        fake.publishResult = AuthResult.TransportFailure

        vm.publish()
        advanceUntilIdle()
        assertTrue(vm.state.value.publishing)
        assertEquals("error.network.unreachable", vm.state.value.failure?.messageKey)

        fake.publishResult = AuthResult.Ok(owner(status = "published", publishable = true))
        vm.retry()
        advanceUntilIdle()
        assertEquals(2, fake.published.size)
        assertFalse(vm.state.value.publishing)
    }

    @Test
    fun unpublish_hides_and_reports() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(status = "published", publishable = true))
        fake.unpublishResult = AuthResult.Ok(owner(status = "hidden", publishable = true))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()

        vm.unpublish()
        advanceUntilIdle()

        assertEquals(1, fake.unpublished)
        assertEquals(ListingStatus.HIDDEN, assertIs<HubListingUiState.Editing>(vm.state.value.body).status)
        assertEquals(HubNotice.UNPUBLISHED, vm.state.value.notice)
    }

    @Test
    fun a_failed_read_is_an_error_with_retry() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.TransportFailure
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()

        val error = assertIs<HubListingUiState.Error>(vm.state.value.body)
        assertTrue(error.retryable)
        assertEquals("error.network.unreachable", error.messageKey)

        fake.listing = AuthResult.Ok(owner())
        vm.retry()
        advanceUntilIdle()
        assertIs<HubListingUiState.Editing>(vm.state.value.body)
    }

    @Test
    fun the_street_address_is_for_centres_only_and_is_the_servers_flag() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(isCentre = false))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        assertFalse(vm.state.value.showStreet)

        fake.listing = AuthResult.Ok(owner(isCentre = true))
        val centre = model(fake)
        centre.load()
        advanceUntilIdle()
        assertTrue(centre.state.value.showStreet)
    }

    @Test
    fun the_runs_classes_badge_is_the_servers_flag() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(runsClasses = true))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        assertTrue(assertIs<HubListingUiState.Editing>(vm.state.value.body).runsClasses)
    }

    @Test
    fun the_slug_check_reports_available_taken_and_failure() = runTest(dispatcher) {
        val fake = FakeHubApi()
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit { it.copy(slug = " rahima-physics ") }

        vm.checkSlug()
        advanceUntilIdle()
        assertEquals(listOf("rahima-physics"), fake.slugsChecked)
        assertEquals(SlugNote.AVAILABLE, vm.state.value.slugNote)

        fake.slug = AuthResult.Ok(SlugAvailability("rahima-physics", available = false))
        vm.checkSlug()
        advanceUntilIdle()
        assertEquals(SlugNote.TAKEN, vm.state.value.slugNote)

        vm.edit { it.copy(slug = "other") }
        assertNull(vm.state.value.slugNote, "editing the slug clears the old answer")

        fake.slug = AuthResult.TransportFailure
        vm.checkSlug()
        advanceUntilIdle()
        assertEquals("error.network.unreachable", vm.state.value.failure?.messageKey)
        assertFalse(vm.state.value.failure!!.canRetry)
    }

    @Test
    fun areas_load_division_then_district_then_upazila_from_the_server() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(districtCode = "BD2019", upazilaCode = "BD201901"))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()

        assertEquals(listOf("BD10", "BD20"), vm.state.value.areas.divisions.map { it.code })
        assertEquals("BD20", vm.state.value.areas.divisionCode, "the division a saved district sits in")
        assertEquals(listOf("BD2019", "BD2020"), vm.state.value.areas.districts.map { it.code })
        assertEquals(listOf("BD201901"), vm.state.value.areas.upazilas.map { it.code })

        vm.pickDivision("BD10")
        advanceUntilIdle()
        assertEquals("", vm.state.value.draft.districtCode, "a new division clears the district")
        assertEquals("", vm.state.value.draft.upazilaCode)
        assertEquals(listOf("BD1001"), vm.state.value.areas.districts.map { it.code })
        assertTrue(vm.state.value.areas.upazilas.isEmpty())

        vm.pickDistrict("BD1001")
        advanceUntilIdle()
        vm.pickUpazila("BD100101")
        assertEquals("BD100101", vm.state.value.draft.upazilaCode)

        vm.save()
        advanceUntilIdle()
        val sent = fake.saved.single()
        assertEquals("BD1001", sent.districtCode)
        assertEquals("BD100101", sent.upazilaCode, "district and upazila travel together")
    }

    @Test
    fun a_city_corporation_offers_its_thanas_and_a_saved_thana_reopens_under_its_city() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(districtCode = "BD2020", upazilaCode = "MT2020500001"))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()

        // The saved thana's city corporation is found and both are shown chosen.
        assertEquals("BD20205000", vm.state.value.areas.cityCode)
        assertEquals(listOf("MT2020500001", "MT2020500002"), vm.state.value.areas.thanas.map { it.code })
        assertEquals("MT2020500001", vm.state.value.draft.upazilaCode)

        // Leaving the thana blank keeps the city corporation.
        vm.pickThana("")
        assertEquals("BD20205000", vm.state.value.draft.upazilaCode)
        vm.pickThana("MT2020500002")
        assertEquals("MT2020500002", vm.state.value.draft.upazilaCode)
        vm.save()
        advanceUntilIdle()
        assertEquals("MT2020500002", fake.saved.single().upazilaCode, "the thana is stored in the upazila slot")

        // An upazila closes the thana level; a city corporation opens it.
        vm.pickUpazila("BD202001")
        assertEquals("", vm.state.value.areas.cityCode)
        assertTrue(vm.state.value.areas.thanas.isEmpty())
        vm.pickUpazila("BD20205000")
        advanceUntilIdle()
        assertEquals("BD20205000", vm.state.value.areas.cityCode)
        assertEquals("BD20205000", vm.state.value.draft.upazilaCode)
        assertEquals(2, vm.state.value.areas.thanas.size)

        // A new district starts the area below it again.
        vm.pickDistrict("BD2019")
        assertEquals("", vm.state.value.areas.cityCode)
        assertTrue(vm.state.value.areas.thanas.isEmpty())
    }

    @Test
    fun an_area_load_failure_shows_an_error_with_retry_not_an_empty_list() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.areasFail = true
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()

        assertTrue(vm.state.value.areas.failed)
        assertTrue(vm.state.value.areas.divisions.isEmpty())

        fake.areasFail = false
        vm.retryAreas()
        advanceUntilIdle()
        assertFalse(vm.state.value.areas.failed)
        assertEquals(2, vm.state.value.areas.divisions.size)
    }

    @Test
    fun the_draft_diff_omits_what_did_not_change_and_clears_with_empty_text() {
        val saved = owner(headlineEn = "Old", slug = "old-slug")
        val draft = draftOf(saved)
        assertNull(updateBody(draft, saved))

        val body = assertNotNull(updateBody(draft.copy(headlineEn = "", phone = " 01711000000 "), saved))
        assertEquals("", body.headlineEn)
        assertEquals("01711000000", body.publicContactPhone)
        assertNull(body.slug)
        assertNull(body.teachingMode)
    }

    @Test
    fun the_latin_name_is_sent_trimmed_only_when_it_changed() {
        val saved = owner().copy(publicNameLatin = "Rahima")
        val draft = draftOf(saved)
        assertEquals("Rahima", draft.publicNameLatin)
        assertNull(updateBody(draft.copy(publicNameLatin = " Rahima "), saved))

        val body = assertNotNull(updateBody(draft.copy(publicNameLatin = " Rahima Akter "), saved))
        assertEquals("Rahima Akter", body.publicNameLatin)
        assertNull(body.publicName)
        val cleared = assertNotNull(updateBody(draft.copy(publicNameLatin = ""), saved))
        assertEquals("", cleared.publicNameLatin)
    }

    @Test
    fun the_servers_fallback_label_is_shown_in_the_readers_language() {
        assertEquals(
            "Rahima, সেন্টারের শিক্ষকবৃন্দ",
            teacherLine(listOf("Rahima", "Centre faculty"), centreFaculty = "সেন্টারের শিক্ষকবৃন্দ"),
        )
    }

    @Test
    fun reentering_the_screen_keeps_unsaved_edits_and_the_retry_banner() = runTest(dispatcher) {
        val fake = FakeHubApi()
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit { it.copy(headlineEn = "typed") }
        fake.saveResult = AuthResult.TransportFailure
        vm.save()
        advanceUntilIdle()
        assertNotNull(vm.state.value.failure)

        vm.load()
        advanceUntilIdle()

        assertEquals("typed", vm.state.value.draft.headlineEn, "a second load does not overwrite the draft")
        assertNotNull(vm.state.value.failure, "nor clear the Retry banner")
    }

    @Test
    fun a_second_write_is_refused_while_one_is_in_flight() = runTest(dispatcher) {
        val fake = FakeHubApi()
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit { it.copy(headlineEn = "x") }

        vm.save()
        vm.save()
        advanceUntilIdle()

        assertEquals(1, fake.saved.size)
    }

    @Test
    fun retry_needs_a_retryable_failure_and_a_non_retryable_one_forgets_the_write() = runTest(dispatcher) {
        val fake = FakeHubApi()
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.edit { it.copy(slug = "taken") }
        fake.saveResult = refusal("hub.slug_taken")
        vm.save()
        advanceUntilIdle()
        assertTrue(vm.state.value.failure!!.saveFailed, "the save banner says nothing typed is lost")

        vm.retry()
        advanceUntilIdle()
        assertEquals(1, fake.saved.size, "the server said repeating cannot help")
    }

    @Test
    fun writes_and_area_picks_are_ignored_unless_the_listing_is_editable() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(status = "suspended"))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()

        vm.unpublish()
        vm.pickDivision("BD10")
        vm.pickDistrict("BD1001")
        advanceUntilIdle()

        assertEquals(0, fake.unpublished)
        assertEquals("", vm.state.value.areas.divisionCode.takeIf { it == "BD10" } ?: "")
        assertEquals("", vm.state.value.draft.districtCode)
    }

    @Test
    fun an_unknown_status_is_never_editable() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(status = "archived"))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()

        assertFalse(vm.state.value.body is HubListingUiState.Editing)
        assertFalse(vm.state.value.canSave)
        assertEquals(ListingStatus.UNKNOWN, ListingStatus.fromWire("archived"))
    }

    @Test
    fun an_outdated_consent_reloads_the_listing_and_keeps_what_was_typed() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(publishable = true, consentVersionCurrent = "2026-11-14"))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.openPublish()
        vm.agree(true)
        fake.listing = AuthResult.Ok(owner(publishable = true, consentVersionCurrent = "2027-01-01"))
        fake.publishResult = refusal("hub.consent_outdated")

        vm.publish()
        advanceUntilIdle()

        assertEquals(2, fake.listingReads, "the refusal reads the listing again, past the re-entry guard")
        val editing = assertIs<HubListingUiState.Editing>(vm.state.value.body)
        assertEquals("2027-01-01", editing.listing.consentVersionCurrent)
        assertEquals("hub.consent_outdated", vm.state.value.failure?.messageKey)
        assertTrue(vm.state.value.publishing, "the sheet stays open on the new terms")
        assertFalse(vm.state.value.agreed, "new terms need a new agreement")

        fake.publishResult = null
        vm.agree(true)
        vm.publish()
        advanceUntilIdle()
        assertEquals(listOf("2026-11-14", "2027-01-01"), fake.published)
    }

    @Test
    fun an_outdated_consent_reload_never_overwrites_unsaved_edits() = runTest(dispatcher) {
        val fake = FakeHubApi()
        fake.listing = AuthResult.Ok(owner(publishable = true))
        val vm = model(fake)
        vm.load()
        advanceUntilIdle()
        vm.openPublish()
        vm.agree(true)
        vm.edit { it.copy(headlineEn = "typed, not saved") }
        fake.listing = AuthResult.Ok(owner(publishable = true, consentVersionCurrent = "2027-01-01"))
        fake.publishResult = refusal("hub.consent_outdated")

        vm.publish()
        advanceUntilIdle()

        assertEquals(2, fake.listingReads)
        assertEquals("typed, not saved", vm.state.value.draft.headlineEn)
    }
}
