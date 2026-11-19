package com.shikkhokplus.app.feature.hublisting

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The message key for a request that never got an answer. */
internal const val HUB_OFFLINE_KEY: String = "error.network.unreachable"

/** The refusal that means the consent terms changed since the listing was read. */
internal const val HUB_CONSENT_OUTDATED_KEY: String = "hub.consent_outdated"

/** The area kind whose children are offered as a third, optional level. */
internal const val AREA_CITY_CORPORATION: String = "city_corporation"

/**
 * A failed call, as the screen shows it.
 *
 * @property messageKey Names a string resource; the server's key, or the offline key
 * @property canRetry Whether repeating the same call can help
 * @property saveFailed Whether this was a save, so the banner can say nothing typed is lost
 */
data class HubFailure(val messageKey: String, val canRetry: Boolean, val saveFailed: Boolean = false)

/**
 * Read a failed [AuthResult] as a [HubFailure].
 *
 * @return The failure, or null for a success
 */
internal fun AuthResult<*>.hubFailure(): HubFailure? =
    when (this) {
        is AuthResult.Ok -> null
        is AuthResult.Refused -> HubFailure(envelope.error.messageKey, envelope.error.retryable)
        AuthResult.TransportFailure -> HubFailure(HUB_OFFLINE_KEY, canRetry = true)
    }

/** What the listing screen renders, mapped from the server's answer. */
sealed interface HubListingUiState {
    /** Waiting for the listing. */
    data object Loading : HubListingUiState

    /**
     * An editable listing; everything it shows beyond the fields is the server's.
     *
     * @property listing The server's listing
     * @property checklist Each requirement and whether the server counts it met
     * @property publishable Whether the server says every requirement is met
     */
    data class Editing(
        val listing: OwnerListingResponse,
        val checklist: List<HubChecklistItem>,
        val publishable: Boolean,
    ) : HubListingUiState {
        /** The listing's status. */
        val status: ListingStatus get() = ListingStatus.fromWire(listing.status)

        /** Whether the server says the owner earns the Runs classes badge. */
        val runsClasses: Boolean get() = listing.runsClasses
    }

    /**
     * A suspended listing: shown, never edited, with how to appeal.
     *
     * @property listing The server's listing
     */
    data class Suspended(val listing: OwnerListingResponse) : HubListingUiState

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Whether to offer a retry
     */
    data class Error(val messageKey: String, val retryable: Boolean) : HubListingUiState
}

/**
 * Map the listing response to what the screen renders. Pure: nothing is
 * decided here beyond which state the server's `status` names.
 *
 * @return Suspended for a suspended listing, an error for an unknown status, else the editor
 */
fun OwnerListingResponse.toUiState(): HubListingUiState =
    when (ListingStatus.fromWire(status)) {
        ListingStatus.SUSPENDED -> HubListingUiState.Suspended(this)
        // A status this version cannot read is never edited from here.
        ListingStatus.UNKNOWN -> HubListingUiState.Error("error.unexpected", retryable = false)
        else -> HubListingUiState.Editing(this, checklist, publishable)
    }

/** The answer to "is this web address free". */
enum class SlugNote {
    /** Nobody holds it. */
    AVAILABLE,

    /** Someone else does, or it is not well formed. */
    TAKEN,
}

/** A short confirmation for the snackbar. */
enum class HubNotice {
    /** A save landed. */
    SAVED,

    /** The listing is now public. */
    PUBLISHED,

    /** The listing is no longer public. */
    UNPUBLISHED,
}

/**
 * The area lists, each read from the server.
 *
 * @property divisions Every division
 * @property districts The districts of [divisionCode]
 * @property upazilas The upazilas, then the city corporations, of the chosen district
 * @property divisionCode The chosen division, or empty
 * @property failed Whether the last area read failed; shown with Retry, never as an empty list
 * @property cityCode The city corporation whose thanas are offered, or empty
 * @property thanas The thanas of [cityCode]
 */
data class AreasState(
    val divisions: List<AreaOption> = emptyList(),
    val districts: List<AreaOption> = emptyList(),
    val upazilas: List<AreaOption> = emptyList(),
    val divisionCode: String = "",
    val failed: Boolean = false,
    val cityCode: String = "",
    val thanas: List<AreaOption> = emptyList(),
)

/**
 * The listing editor.
 *
 * @property body What the server said the listing is
 * @property draft What the owner has typed
 * @property saving Whether a write is in flight
 * @property failure The last failed call, or null
 * @property slugNote The answer to the last slug check, or null
 * @property publishing Whether the consent sheet is open
 * @property agreed Whether its box is ticked
 * @property notice A confirmation to show once, or null
 * @property areas The area pickers' lists
 * @property switchSaving Whether the join-requests switch is being saved
 * @property switchFailure Why the last switch save failed, or null
 */
data class HubListingState(
    val body: HubListingUiState = HubListingUiState.Loading,
    val draft: HubDraft = HubDraft(),
    val saving: Boolean = false,
    val failure: HubFailure? = null,
    val slugNote: SlugNote? = null,
    val publishing: Boolean = false,
    val agreed: Boolean = false,
    val notice: HubNotice? = null,
    val areas: AreasState = AreasState(),
    val switchSaving: Boolean = false,
    val switchFailure: HubFailure? = null,
) {
    private val saved: OwnerListingResponse?
        get() =
            when (body) {
                is HubListingUiState.Editing -> body.listing
                is HubListingUiState.Suspended -> body.listing
                else -> null
            }

    private val editing: HubListingUiState.Editing? get() = body as? HubListingUiState.Editing

    /** Whether the owner has typed something not yet saved. */
    val dirty: Boolean get() = saved?.let { updateBody(draft, it) != null } ?: false

    /** Whether Save is offered. */
    val canSave: Boolean get() = editing != null && dirty && !saving

    /** Whether Publish is offered: the server's `publishable`, with nothing unsaved. */
    val canPublish: Boolean
        get() = editing?.let { it.publishable && !dirty && !saving && it.status != ListingStatus.PUBLISHED } ?: false

    /** Whether Unpublish is offered. */
    val canUnpublish: Boolean
        get() = editing?.let { it.status == ListingStatus.PUBLISHED && !dirty && !saving } ?: false

    /**
     * Whether the join-requests switch is drawn: only while the server says
     * `enquiries_offered` [H5]. Switched off, the owner is offered nothing.
     */
    val offersEnquiries: Boolean get() = saved?.enquiriesOffered == true

    /** Whether the street address is asked for: the server's `is_centre`. */
    val showStreet: Boolean get() = saved?.isCentre == true

    /**
     * The slug "View public page" opens, offered only while the server says
     * the listing is published and has one; null otherwise.
     */
    val publicSlug: String?
        get() = editing?.takeIf { it.status == ListingStatus.PUBLISHED }?.listing?.slug?.ifBlank { null }
}

/** The write a Retry repeats. */
private enum class HubWrite { SAVE, PUBLISH, UNPUBLISH }

/**
 * Holds the owner's listing: read, edit, save, publish and unpublish.
 *
 * It renders the server's decisions and sends the owner's words. A failed
 * write keeps everything typed and offers the same call again; nothing is
 * queued [TC-8, D-9].
 *
 * @property api The network
 */
class HubListingViewModel(
    private val api: HubApi,
) : ViewModel() {

    private val _state = MutableStateFlow(HubListingState())

    /** What the screen renders. */
    val state: StateFlow<HubListingState> = _state.asStateFlow()

    private var lastWrite: HubWrite? = null

    /** What the join-requests switch was last asked to become, for its Retry. */
    private var switchWanted: Boolean? = null

    /**
     * Read the listing, then the areas it needs. Does nothing once a listing
     * is showing, so re-entering the screen (rotation, coming back from the
     * batch listings) never overwrites unsaved edits or a Retry banner.
     */
    fun load() {
        val body = _state.value.body
        if (body is HubListingUiState.Editing || body is HubListingUiState.Suspended) return
        viewModelScope.launch {
            when (val result = api.listing()) {
                is AuthResult.Ok -> {
                    apply(result.value)
                    loadAreas()
                }
                else ->
                    result.hubFailure()?.let { f ->
                        _state.update { it.copy(body = HubListingUiState.Error(f.messageKey, f.canRetry)) }
                    }
            }
        }
    }

    /** Repeat what last failed: the read, or the write. */
    fun retry() {
        if (_state.value.body is HubListingUiState.Error) {
            _state.update { it.copy(body = HubListingUiState.Loading) }
            load()
            return
        }
        if (_state.value.failure?.canRetry != true) return
        when (lastWrite) {
            HubWrite.SAVE -> save()
            HubWrite.PUBLISH -> publish()
            HubWrite.UNPUBLISH -> unpublish()
            null -> Unit
        }
    }

    /**
     * Change what the owner has typed. Ignored unless the listing can be edited.
     *
     * @param change The edit to the draft
     */
    fun edit(change: (HubDraft) -> HubDraft) {
        _state.update {
            if (it.body !is HubListingUiState.Editing) return@update it
            val next = change(it.draft)
            it.copy(draft = next, slugNote = if (next.slug == it.draft.slug) it.slugNote else null)
        }
    }

    /**
     * Tick or untick a teaching mode.
     *
     * @param mode The mode
     * @param on Whether it is chosen
     */
    fun toggleMode(mode: TeachingMode, on: Boolean) =
        edit { d -> d.copy(modes = if (on) (d.modes - mode.wire) + mode.wire else d.modes - mode.wire) }

    /** Send what changed. */
    fun save() {
        val current = _state.value
        val saved = (current.body as? HubListingUiState.Editing)?.listing ?: return
        val body = updateBody(current.draft, saved)
        if (body == null || current.saving) return
        lastWrite = HubWrite.SAVE
        _state.update { it.copy(saving = true, failure = null) }
        viewModelScope.launch { finish(api.save(body), HubNotice.SAVED, saved = true) }
    }

    /** Ask whether the typed web address is free. */
    fun checkSlug() {
        val slug = _state.value.draft.slug.trim()
        if (slug.isEmpty()) return
        _state.update { it.copy(slugNote = null) }
        viewModelScope.launch {
            val result = api.slugAvailable(slug)
            val answer = (result as? AuthResult.Ok)?.value
            _state.update {
                when {
                    answer != null ->
                        it.copy(slugNote = if (answer.available) SlugNote.AVAILABLE else SlugNote.TAKEN)
                    else -> it.copy(failure = result.hubFailure()?.copy(canRetry = false))
                }
            }
        }
    }

    /** Open the consent sheet, when Publish is offered. */
    fun openPublish() = _state.update { if (it.canPublish) it.copy(publishing = true, agreed = false) else it }

    /** Close the consent sheet. */
    fun closePublish() = _state.update { it.copy(publishing = false, agreed = false, failure = null) }

    /**
     * Tick or untick the consent box.
     *
     * @param value Whether the owner agrees
     */
    fun agree(value: Boolean) = _state.update { it.copy(agreed = value) }

    /** Publish, sending the consent version the server named in its last answer. */
    fun publish() {
        val current = _state.value
        val editing = current.body as? HubListingUiState.Editing ?: return
        if (!current.publishing || !current.agreed || current.saving) return
        lastWrite = HubWrite.PUBLISH
        _state.update { it.copy(saving = true, failure = null) }
        viewModelScope.launch {
            finish(api.publish(editing.listing.consentVersionCurrent), HubNotice.PUBLISHED)
        }
    }

    /** Take the listing down; the text is kept. */
    fun unpublish() {
        if (_state.value.body !is HubListingUiState.Editing || _state.value.saving) return
        lastWrite = HubWrite.UNPUBLISH
        _state.update { it.copy(saving = true, failure = null) }
        viewModelScope.launch { finish(api.unpublish(), HubNotice.UNPUBLISHED) }
    }

    /**
     * Turn join requests on or off [H5]. Saved the moment it changes, and on
     * its own: only `accepts_enquiries` is sent, and only the server's
     * listing is replaced, so whatever the owner typed is neither sent nor
     * lost. A failure leaves the switch at what the server holds and offers
     * Retry when trying again can help [TC-8].
     *
     * @param on Whether to receive join requests
     */
    fun setAcceptsEnquiries(on: Boolean) {
        val current = _state.value
        if (current.body !is HubListingUiState.Editing || !current.offersEnquiries || current.switchSaving) return
        switchWanted = on
        _state.update { it.copy(switchSaving = true, switchFailure = null) }
        viewModelScope.launch {
            val result = api.save(OwnerListingUpdateRequest(acceptsEnquiries = on))
            _state.update {
                when (result) {
                    is AuthResult.Ok -> it.copy(body = result.value.toUiState(), switchSaving = false)
                    else -> it.copy(switchSaving = false, switchFailure = result.hubFailure())
                }
            }
        }
    }

    /** Save the switch again, after a failure that can be retried. */
    fun retrySwitch() {
        val wanted = switchWanted ?: return
        if (_state.value.switchFailure?.canRetry == true) setAcceptsEnquiries(wanted)
    }

    /** Forget the confirmation once it has been shown. */
    fun dismissNotice() = _state.update { it.copy(notice = null) }

    /**
     * Choose a division; the district and upazila are chosen again.
     *
     * @param code The division's code
     */
    fun pickDivision(code: String) {
        if (_state.value.body !is HubListingUiState.Editing) return
        _state.update {
            it.copy(
                draft = it.draft.copy(districtCode = "", upazilaCode = ""),
                areas =
                    it.areas.copy(
                        divisionCode = code,
                        districts = emptyList(),
                        upazilas = emptyList(),
                        cityCode = "",
                        thanas = emptyList(),
                    ),
            )
        }
        if (code.isNotEmpty()) {
            viewModelScope.launch {
                readAreas(code)?.let { list -> _state.update { it.copy(areas = it.areas.copy(districts = list)) } }
            }
        }
    }

    /**
     * Choose a district; the upazila is chosen again.
     *
     * @param code The district's code
     */
    fun pickDistrict(code: String) {
        if (_state.value.body !is HubListingUiState.Editing) return
        _state.update {
            it.copy(
                draft = it.draft.copy(districtCode = code, upazilaCode = ""),
                areas = it.areas.copy(upazilas = emptyList(), cityCode = "", thanas = emptyList()),
            )
        }
        if (code.isNotEmpty()) {
            viewModelScope.launch {
                readAreas(code)?.let { list -> _state.update { it.copy(areas = it.areas.copy(upazilas = list)) } }
            }
        }
    }

    /**
     * Choose an upazila or a city corporation; a city corporation offers its thanas.
     *
     * @param code The upazila's or city corporation's code
     */
    fun pickUpazila(code: String) {
        if (_state.value.body !is HubListingUiState.Editing) return
        val city = _state.value.areas.upazilas.any { it.code == code && it.kind == AREA_CITY_CORPORATION }
        _state.update {
            it.copy(
                draft = it.draft.copy(upazilaCode = code),
                areas = it.areas.copy(cityCode = if (city) code else "", thanas = emptyList()),
            )
        }
        if (city) {
            viewModelScope.launch {
                readAreas(code)?.let { list ->
                    // Dropped if another area was picked while this read was in flight.
                    _state.update {
                        if (it.areas.cityCode == code) it.copy(areas = it.areas.copy(thanas = list)) else it
                    }
                }
            }
        }
    }

    /**
     * Choose a thana of the chosen city corporation; empty keeps the city corporation.
     *
     * @param code The thana's code, or empty for the whole city corporation
     */
    fun pickThana(code: String) {
        val city = _state.value.areas.cityCode
        if (city.isEmpty()) return
        edit { it.copy(upazilaCode = code.ifEmpty { city }) }
    }

    /** Read the area lists again after a failure. */
    fun retryAreas() {
        _state.update { it.copy(areas = it.areas.copy(failed = false)) }
        loadAreas()
    }

    private fun apply(listing: OwnerListingResponse, notice: HubNotice? = null) =
        _state.update {
            it.copy(
                body = listing.toUiState(),
                draft = draftOf(listing),
                saving = false,
                failure = null,
                publishing = false,
                agreed = false,
                notice = notice,
            )
        }

    private fun finish(result: AuthResult<OwnerListingResponse>, notice: HubNotice, saved: Boolean = false) {
        when (result) {
            is AuthResult.Ok -> apply(result.value, notice)
            else -> {
                val failure = result.hubFailure()?.copy(saveFailed = saved)
                // A failure repeating cannot fix leaves nothing to retry.
                if (failure?.canRetry != true) lastWrite = null
                _state.update { it.copy(saving = false, failure = failure) }
                if (failure?.messageKey == HUB_CONSENT_OUTDATED_KEY) reloadTerms()
            }
        }
    }

    /**
     * Read the listing again for the consent version the server now names.
     *
     * An explicit refresh, past [load]'s re-entry guard: only the server's
     * listing is replaced, so whatever the owner typed is kept, and the box
     * is unticked because new terms need a new agreement. The sheet stays
     * open with the refusal showing.
     */
    private fun reloadTerms() {
        viewModelScope.launch {
            val fresh = (api.listing() as? AuthResult.Ok)?.value ?: return@launch
            _state.update { it.copy(body = fresh.toUiState(), agreed = false) }
        }
    }

    private fun loadAreas() {
        viewModelScope.launch {
            val divisions = readAreas(null) ?: return@launch
            val draft = _state.value.draft
            val division =
                _state.value.areas.divisionCode.ifEmpty { divisionOf(draft.districtCode, divisions.map { it.code }) }
            val districts = if (division.isEmpty()) emptyList() else readAreas(division).orEmpty()
            val upazilas = if (draft.districtCode.isEmpty()) emptyList() else readAreas(draft.districtCode).orEmpty()
            val (city, thanas) = cityOf(draft.upazilaCode, upazilas)
            _state.update {
                it.copy(areas = AreasState(divisions, districts, upazilas, division, it.areas.failed, city, thanas))
            }
        }
    }

    /**
     * The city corporation a saved code sits in, with its thanas.
     *
     * The code is either a city corporation in [upazilas], or a thana of
     * one of them; the thanas of the district's city corporations are read
     * until one holds it.
     *
     * @param code The saved upazila-slot code
     * @param upazilas The district's upazilas and city corporations
     * @return The city corporation's code and its thanas, or empty for neither
     */
    private suspend fun cityOf(code: String, upazilas: List<AreaOption>): Pair<String, List<AreaOption>> {
        val direct = upazilas.firstOrNull { it.code == code }
        val cities =
            when {
                code.isEmpty() -> emptyList()
                direct == null -> upazilas.filter { it.kind == AREA_CITY_CORPORATION }
                direct.kind == AREA_CITY_CORPORATION -> listOf(direct)
                else -> emptyList()
            }
        var found = "" to emptyList<AreaOption>()
        val pending = cities.iterator()
        while (found.first.isEmpty() && pending.hasNext()) {
            val city = pending.next()
            // A failed read is already marked; the person retries from the banner.
            val thanas = readAreas(city.code) ?: break
            if (city == direct || thanas.any { it.code == code }) found = city.code to thanas
        }
        return found
    }

    /** One level of the area list, or null after marking the read failed. */
    private suspend fun readAreas(parent: String?): List<AreaOption>? =
        when (val result = api.areas(parent)) {
            is AuthResult.Ok -> result.value
            else -> {
                _state.update { it.copy(areas = it.areas.copy(failed = true)) }
                null
            }
        }
}
