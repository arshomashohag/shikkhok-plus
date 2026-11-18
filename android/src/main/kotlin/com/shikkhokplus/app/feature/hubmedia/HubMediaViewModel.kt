package com.shikkhokplus.app.feature.hubmedia

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.HubFailure
import com.shikkhokplus.app.feature.hublisting.hubFailure
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.IOException

/** The owner's own gallery holds twelve photos, as the server counts them. */
const val OWNER_PHOTO_LIMIT: Int = 12

/** A batch's gallery holds eight. */
const val BATCH_PHOTO_LIMIT: Int = 8

/** The server's ceiling on one file; checked here only to answer before a pointless upload. */
const val MAX_UPLOAD_BYTES: Long = 8L * 1024 * 1024

/** The server's limit on each alt text (`MediaComplete`). */
const val ALT_MAX: Int = 200

/** How often `complete` is asked again while the file is still being read. */
const val POLL_INTERVAL_MS: Long = 2_000

/** How long it is asked before the screen offers Check again. */
const val POLL_LIMIT_MS: Long = 60_000

/** The three types the server takes. */
private val UPLOAD_TYPES: Set<String> = setOf("image/jpeg", "image/png", "image/webp")

/** The statuses that free a slot, as the server's quota reads them. */
private val UNCOUNTED: Set<String> = setOf("rejected", "withdrawn")

/** Whether a photo holds one of its gallery's slots. */
private fun MediaResponse.counts(): Boolean = status !in UNCOUNTED

private const val NOT_UPLOADED_CODE = "MEDIA_NOT_UPLOADED"
private const val NOT_UPLOADED_KEY = "hub.media.not_uploaded"
private const val ALT_INVALID_KEY = "hub.media.alt_invalid"

/**
 * Where the photo being added is. The six states of the editor.
 */
sealed interface PhotoUpload {
    /** Nothing is being added. */
    data object Idle : PhotoUpload

    /** The photo picker is open. */
    data object Picking : PhotoUpload

    /** The file is being read, signed and posted to the bucket. */
    data object Uploading : PhotoUpload

    /** The file is posted and `complete` is being asked until it is read and sent for review. */
    data object WaitingReview : PhotoUpload

    /**
     * The photo was not added.
     *
     * @property failure The server's key and whether repeating can help
     * @property slow Whether this is the minute's poll running out, with the file still unread
     */
    data class Failed(val failure: HubFailure, val slow: Boolean = false) : PhotoUpload

    /** The photo is with the moderators. */
    data object Done : PhotoUpload
}

/**
 * The photos screen.
 *
 * @property batchId The batch whose gallery this is; null for the owner's own
 * @property readOnly Whether the listing is suspended, so nothing can change
 *   but a delete: a suspended listing's photo keeps its public link until
 *   its owner removes it, and the server never refuses that
 * @property photos The server's list, or null until it has been read
 * @property loadFailure Why the list could not be read, or null
 * @property altEn The English alt text as typed
 * @property altBn The Bangla alt text as typed
 * @property upload Where the photo being added is
 * @property busy Whether a reorder or delete is in flight
 * @property failure Why the last reorder or delete failed, or null
 * @property deleting The photo whose deletion is being confirmed, or null
 */
data class HubPhotosState(
    val batchId: String?,
    val readOnly: Boolean = false,
    val photos: List<MediaResponse>? = null,
    val loadFailure: HubFailure? = null,
    val altEn: String = "",
    val altBn: String = "",
    val upload: PhotoUpload = PhotoUpload.Idle,
    val busy: Boolean = false,
    val failure: HubFailure? = null,
    val deleting: MediaResponse? = null,
) {
    /** How many photos the gallery holds: the server's, never counted here. */
    val limit: Int get() = if (batchId == null) OWNER_PHOTO_LIMIT else BATCH_PHOTO_LIMIT

    /**
     * How many listed photos hold a slot: every status but rejected and
     * withdrawn, as the server counts (it already leaves out an upload
     * abandoned past its window).
     */
    val count: Int get() = photos?.count { it.counts() } ?: 0

    /** Whether a photo is being added right now, so the form is locked. */
    val inFlight: Boolean
        get() = upload == PhotoUpload.Picking || upload == PhotoUpload.Uploading || upload == PhotoUpload.WaitingReview

    /** Whether the retry on a failed upload polls `complete` again rather than uploading. */
    val checkAgain: Boolean get() = (upload as? PhotoUpload.Failed)?.slow == true
}

/**
 * A photo on its way: the file, the alt texts it was chosen with, and how
 * far it got, so a retry resumes rather than starting over.
 *
 * @property contentType The file's type
 * @property bytes The file
 * @property altEn English alt text, trimmed
 * @property altBn Bangla alt text, trimmed
 * @property ticket The signed form, once the server issued one and the bucket has not refused it
 * @property uploaded Whether the bucket took the file, so only `complete` remains
 */
private data class Pending(
    val contentType: String,
    val bytes: ByteArray,
    val altEn: String,
    val altBn: String,
    val ticket: MediaUploadTicket? = null,
    val uploaded: Boolean = false,
)

/**
 * Holds one gallery's photos and the photo being added to it.
 *
 * **Every rule is the server's.** Type and size are pre-checked only so a
 * pointless upload is answered at once, in the server's own words; the
 * quota counts the listed photos the server counts; a reorder names only
 * those, and the server keeps the rest after them; `thumb_url` is used as
 * it arrives.
 *
 * **The file goes to the bucket, not through the API**, on a client that
 * carries no session ([BucketClient]). Then `complete` is asked every two
 * seconds for up to a minute while the server answers `MEDIA_NOT_UPLOADED`
 * (the file is still being read). Past the minute Check again polls again
 * and never uploads a second time. Any other answer ends the poll.
 *
 * **A dropped connection keeps everything** -- the typed alt texts, the
 * file, the ticket -- and Retry picks up where it stopped [TC-8].
 *
 * @property api The network
 * @param batchId The batch whose gallery this is; null for the owner's own
 * @param readOnly Whether the listing is suspended
 */
class HubMediaViewModel(
    private val api: HubMediaApi,
    batchId: String?,
    readOnly: Boolean = false,
) : ViewModel() {

    private val _state = MutableStateFlow(HubPhotosState(batchId, readOnly))

    /** What the screen renders. */
    val state: StateFlow<HubPhotosState> = _state.asStateFlow()

    private var pending: Pending? = null
    private var job: Job? = null
    private var lastWrite: (() -> Unit)? = null

    /** Read the gallery; does nothing once it is showing. */
    fun load() {
        if (_state.value.photos != null) return
        refresh()
    }

    /** Read the gallery again after a failed read. */
    fun retryLoad() {
        if (_state.value.loadFailure == null) return
        _state.update { it.copy(loadFailure = null) }
        refresh()
    }

    private fun refresh() {
        viewModelScope.launch {
            val result = api.list(_state.value.batchId)
            _state.update {
                when (result) {
                    is AuthResult.Ok -> it.copy(photos = result.value, loadFailure = null)
                    else -> it.copy(loadFailure = result.hubFailure())
                }
            }
        }
    }

    /**
     * Change the English alt text; anything past the server's limit is not kept.
     *
     * @param text As typed
     */
    fun editAltEn(text: String) {
        if (editable()) _state.update { it.copy(altEn = text.take(ALT_MAX)) }
    }

    /**
     * Change the Bangla alt text; anything past the server's limit is not kept.
     *
     * @param text As typed
     */
    fun editAltBn(text: String) {
        if (editable()) _state.update { it.copy(altBn = text.take(ALT_MAX)) }
    }

    private fun editable(): Boolean = !_state.value.readOnly && !_state.value.inFlight

    /**
     * Ask to open the photo picker.
     *
     * @return True when the picker should open; false when nothing may be
     *   added now, or when an alt text is missing, which is then shown in
     *   the server's words
     */
    fun startPicking(): Boolean {
        val s = _state.value
        if (s.readOnly || s.inFlight) return false
        if (s.altEn.isBlank() || s.altBn.isBlank()) {
            _state.update { it.copy(upload = PhotoUpload.Failed(HubFailure(ALT_INVALID_KEY, false))) }
            return false
        }
        _state.update { it.copy(upload = PhotoUpload.Picking) }
        return true
    }

    /**
     * The picker's answer.
     *
     * @param photo The chosen file, or null when the picker was dismissed
     */
    fun picked(photo: PickedPhoto?) {
        val s = _state.value
        if (s.upload != PhotoUpload.Picking) return
        when {
            photo == null -> _state.update { it.copy(upload = PhotoUpload.Idle) }
            photo.contentType !in UPLOAD_TYPES -> refuse("hub.media.type_not_allowed")
            (photo.byteSize ?: 0L) > MAX_UPLOAD_BYTES -> refuse("hub.media.too_large")
            else -> {
                pending = null
                _state.update { it.copy(upload = PhotoUpload.Uploading) }
                job = viewModelScope.launch { readAndUpload(photo, s.altEn.trim(), s.altBn.trim()) }
            }
        }
    }

    private fun refuse(key: String) =
        _state.update { it.copy(upload = PhotoUpload.Failed(HubFailure(key, canRetry = false))) }

    private suspend fun readAndUpload(photo: PickedPhoto, altEn: String, altBn: String) {
        val bytes =
            try {
                photo.read()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: IOException) {
                null
            } catch (_: RuntimeException) {
                // A provider may throw anything from openInputStream: a revoked
                // grant (SecurityException), a document gone from a cloud
                // provider (IllegalArgumentException, IllegalStateException).
                // Each means this file cannot be read, never a crash.
                null
            }
        when {
            bytes == null || bytes.isEmpty() -> refuse("hub.media.unreadable")
            bytes.size > MAX_UPLOAD_BYTES -> refuse("hub.media.too_large")
            else -> upload(Pending(photo.contentType.orEmpty(), bytes, altEn, altBn))
        }
    }

    /** Sign, post, then poll; each step resumes from what [p] already has. */
    private suspend fun upload(p: Pending) {
        pending = p
        _state.update { it.copy(upload = PhotoUpload.Uploading) }
        val ticket = p.ticket ?: ticketFor(p) ?: return
        pending = p.copy(ticket = ticket)
        when (val sent = api.send(ticket, p.contentType, p.bytes)) {
            is AuthResult.Ok -> poll(p.copy(ticket = ticket, uploaded = true))
            is AuthResult.Refused -> {
                // The bucket refused this form; the next try asks for a new one.
                pending = p.copy(ticket = null)
                fail(sent)
            }
            AuthResult.TransportFailure -> fail(sent)
        }
    }

    /** Ask the server to sign an upload for [p]; on a refusal the failure is shown and null returned. */
    private suspend fun ticketFor(p: Pending): MediaUploadTicket? {
        val init = MediaUploadInit(_state.value.batchId, p.contentType, p.bytes.size.toLong())
        return when (val started = api.startUpload(init)) {
            is AuthResult.Ok -> started.value
            else -> {
                fail(started)
                null
            }
        }
    }

    /** Ask `complete` at once, then every two seconds while the file is unread, for up to a minute. */
    private suspend fun poll(p: Pending) {
        pending = p
        _state.update { it.copy(upload = PhotoUpload.WaitingReview) }
        val mediaId = p.ticket?.mediaId ?: return
        val alts = MediaComplete(p.altEn, p.altBn)
        var waited = 0L
        var result = api.complete(mediaId, alts)
        while (result.isNotUploaded() && waited < POLL_LIMIT_MS) {
            delay(POLL_INTERVAL_MS)
            waited += POLL_INTERVAL_MS
            result = api.complete(mediaId, alts)
        }
        when {
            result is AuthResult.Ok -> done(result.value)
            result.isNotUploaded() ->
                _state.update {
                    it.copy(upload = PhotoUpload.Failed(HubFailure(NOT_UPLOADED_KEY, canRetry = true), slow = true))
                }
            else -> fail(result, reloadOnRefusal = true)
        }
    }

    private fun done(photo: MediaResponse) {
        pending = null
        _state.update { s ->
            val rest = s.photos.orEmpty().filter { it.id != photo.id }
            s.copy(
                photos = (rest + photo).sortedBy { it.position },
                upload = PhotoUpload.Done,
                altEn = "",
                altBn = "",
            )
        }
    }

    private fun fail(result: AuthResult<*>, reloadOnRefusal: Boolean = false) {
        val failure = result.hubFailure() ?: return
        _state.update { it.copy(upload = PhotoUpload.Failed(failure)) }
        if (!failure.canRetry) {
            // A refusal ends this photo; the server's list shows what became of it.
            pending = null
            if (reloadOnRefusal) refresh()
        }
    }

    /** Repeat a failed upload from where it stopped: Check again polls; otherwise it posts again. */
    fun retry() {
        val s = _state.value
        val failed = s.upload as? PhotoUpload.Failed ?: return
        val held = pending
        if (!failed.failure.canRetry || held == null) return
        // The text sent is the text on screen now: the fields stay editable
        // after a failure, and this is public listing text.
        val altEn = s.altEn.trim()
        val altBn = s.altBn.trim()
        if (altEn.isEmpty() || altBn.isEmpty()) {
            // Kept retryable: the photo is still pending, and Retry works once both are typed.
            _state.update { it.copy(upload = PhotoUpload.Failed(HubFailure(ALT_INVALID_KEY, canRetry = true))) }
            return
        }
        val p = held.copy(altEn = altEn, altBn = altBn)
        pending = p
        job = viewModelScope.launch { if (p.uploaded) poll(p) else upload(p) }
    }

    /**
     * Move a photo one place.
     *
     * @param index Its place in the list
     * @param by -1 for up, 1 for down
     */
    fun move(index: Int, by: Int) {
        val s = _state.value
        val ids = s.photos?.map { it.id }?.toMutableList() ?: return
        val other = index + by
        if (s.readOnly || s.busy || !listOf(index, other).all { it in ids.indices }) return
        ids[index] = ids[other].also { ids[other] = ids[index] }
        val counted = s.photos.filter { it.counts() }.map { it.id }.toSet()
        val named = ids.filter { it in counted }
        write {
            when (val result = api.order(s.batchId, named)) {
                is AuthResult.Ok -> _state.update { it.copy(photos = result.value) }
                else -> return@write result
            }
            null
        }
    }

    /**
     * Ask to delete a photo; nothing is deleted until [confirmDelete].
     * Allowed in a read-only gallery too: removing a photo is never refused.
     *
     * @param photo The photo
     */
    fun askDelete(photo: MediaResponse) {
        _state.update { it.copy(deleting = photo) }
    }

    /** Keep the photo. */
    fun cancelDelete() = _state.update { it.copy(deleting = null) }

    /** Delete the photo being confirmed; the dialog closes either way, so a failure is seen. */
    fun confirmDelete() {
        val photo = _state.value.deleting ?: return
        if (_state.value.busy) return
        write {
            val result = api.delete(photo.id)
            _state.update { s ->
                s.copy(
                    photos = if (result is AuthResult.Ok) s.photos?.filter { it.id != photo.id } else s.photos,
                    deleting = null,
                )
            }
            if (result is AuthResult.Ok) null else result
        }
    }

    /** Repeat the reorder or delete that failed. */
    fun retryWrite() {
        if (_state.value.failure?.canRetry == true) lastWrite?.invoke()
    }

    /** Run one reorder or delete; [call] answers the failed result, or null on success. */
    private fun write(call: suspend () -> AuthResult<*>?) {
        lastWrite = { write(call) }
        _state.update { it.copy(busy = true, failure = null) }
        viewModelScope.launch {
            val failed = call()
            _state.update { it.copy(busy = false, failure = failed?.hubFailure()) }
        }
    }

    private fun AuthResult<*>.isNotUploaded(): Boolean =
        this is AuthResult.Refused &&
            (envelope.error.code == NOT_UPLOADED_CODE || envelope.error.messageKey == NOT_UPLOADED_KEY)
}
