package com.shikkhokplus.app.feature.hubmedia

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.HUB_OFFLINE_KEY
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import java.io.IOException
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** A photo as the server answers it; tests override only what they look at. */
internal fun media(
    id: String = PHOTO_A,
    position: Int = 1,
    status: String = "approved",
    batchId: String? = null,
    altEn: String? = "Photo $position",
    thumbUrl: String? = "https://site.example/m/key$position/320.webp",
) = MediaResponse(
    id = id,
    batchId = batchId,
    status = status,
    altEn = altEn,
    altBn = null,
    position = position,
    width = 960,
    height = 640,
    rejectionCode = null,
    thumbUrl = thumbUrl,
)

internal const val PHOTO_A = "a1111111-1111-4111-8111-111111111111"
internal const val PHOTO_B = "b2222222-2222-4222-8222-222222222222"
internal const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"

/** Records every call and answers each with the queued results, the last repeating. */
internal class FakeHubMediaApi : HubMediaApi {
    var lists: ArrayDeque<AuthResult<List<MediaResponse>>> = ArrayDeque(listOf(AuthResult.Ok(emptyList())))
    var inits: ArrayDeque<AuthResult<MediaUploadTicket>> = ArrayDeque(listOf(AuthResult.Ok(TICKET)))
    var sends: ArrayDeque<AuthResult<Unit>> = ArrayDeque(listOf(AuthResult.Ok(Unit)))
    var completes: ArrayDeque<AuthResult<MediaResponse>> =
        ArrayDeque(listOf(AuthResult.Ok(media(status = "pending_review", altEn = "A class"))))
    var orders: ArrayDeque<AuthResult<List<MediaResponse>>> = ArrayDeque(listOf(AuthResult.Ok(emptyList())))
    var deletes: ArrayDeque<AuthResult<Unit>> = ArrayDeque(listOf(AuthResult.Ok(Unit)))

    val listed = mutableListOf<String?>()
    val started = mutableListOf<MediaUploadInit>()
    val sent = mutableListOf<Pair<MediaUploadTicket, Int>>()
    val completed = mutableListOf<Pair<String, MediaComplete>>()
    val ordered = mutableListOf<Pair<String?, List<String>>>()
    val deleted = mutableListOf<String>()

    private fun <T> ArrayDeque<T>.next(): T = if (size > 1) removeFirst() else first()

    override suspend fun list(batchId: String?): AuthResult<List<MediaResponse>> {
        listed += batchId
        return lists.next()
    }

    override suspend fun startUpload(body: MediaUploadInit): AuthResult<MediaUploadTicket> {
        started += body
        return inits.next()
    }

    override suspend fun send(ticket: MediaUploadTicket, contentType: String, bytes: ByteArray): AuthResult<Unit> {
        sent += ticket to bytes.size
        return sends.next()
    }

    override suspend fun complete(mediaId: String, body: MediaComplete): AuthResult<MediaResponse> {
        completed += mediaId to body
        return completes.next()
    }

    override suspend fun order(batchId: String?, ids: List<String>): AuthResult<List<MediaResponse>> {
        ordered += batchId to ids
        return orders.next()
    }

    override suspend fun delete(mediaId: String): AuthResult<Unit> {
        deleted += mediaId
        return deletes.next()
    }

    companion object {
        val TICKET =
            MediaUploadTicket(
                mediaId = PHOTO_A,
                url = "https://bucket.example/",
                fields = linkedMapOf("key" to "quarantine/$PHOTO_A", "policy" to "p"),
                expiresAt = "2026-11-18T10:10:00Z",
            )
    }
}

/**
 * The photo editor's state machine: idle, picking, uploading,
 * waiting_review, failed (retryable or not) and done; the `complete` poll
 * on virtual time; and the server's words for every refusal.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class HubMediaViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun refused(code: String, key: String, retryable: Boolean = false) =
        AuthResult.Refused(ErrorEnvelope(ErrorBody(code, retryable = retryable, messageKey = key)))

    private val notUploaded = refused("MEDIA_NOT_UPLOADED", "hub.media.not_uploaded")

    private fun png(size: Long? = 10, bytes: () -> ByteArray? = { ByteArray(10) }) =
        PickedPhoto(contentType = "image/png", byteSize = size, read = { bytes() })

    /** A loaded editor with both alt texts typed. */
    private fun TestScope.ready(api: FakeHubMediaApi, batchId: String? = null): HubMediaViewModel {
        val vm = HubMediaViewModel(api, batchId)
        vm.load()
        advanceUntilIdle()
        vm.editAltEn(" A class ")
        vm.editAltBn("ক্লাস")
        return vm
    }

    /** Start picking, pick [photo], and let it run to the first wait. */
    private fun TestScope.choose(vm: HubMediaViewModel, photo: PickedPhoto? = png()) {
        assertTrue(vm.startPicking(), "the picker opens")
        assertEquals(PhotoUpload.Picking, vm.state.value.upload)
        vm.picked(photo)
        runCurrent()
    }

    @Test
    fun `upload success`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        val vm = ready(api)
        assertEquals(PhotoUpload.Idle, vm.state.value.upload)

        choose(vm)

        assertEquals(listOf(MediaUploadInit(null, "image/png", 10)), api.started)
        assertEquals(listOf(FakeHubMediaApi.TICKET to 10), api.sent)
        assertEquals(listOf(PHOTO_A to MediaComplete("A class", "ক্লাস")), api.completed)
        val s = vm.state.value
        assertEquals(PhotoUpload.Done, s.upload)
        assertEquals(listOf("pending_review"), s.photos?.map { it.status })
        assertEquals("", s.altEn, "a photo sent for review clears the form")
        assertEquals("", s.altBn)
        assertEquals(1, s.count)
    }

    @Test
    fun `not uploaded then success`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.completes = ArrayDeque(listOf(notUploaded, notUploaded, AuthResult.Ok(media(status = "pending_review"))))
        val vm = ready(api)

        choose(vm)
        assertEquals(PhotoUpload.WaitingReview, vm.state.value.upload)
        assertEquals(1, api.completed.size)

        advanceTimeBy(POLL_INTERVAL_MS + 1)
        assertEquals(2, api.completed.size)
        assertEquals(PhotoUpload.WaitingReview, vm.state.value.upload)

        advanceTimeBy(POLL_INTERVAL_MS)
        assertEquals(3, api.completed.size)
        assertEquals(PhotoUpload.Done, vm.state.value.upload)
        assertEquals(1, api.sent.size, "the file is posted once")
    }

    @Test
    fun `the poll stops at a minute and Check again polls without uploading again`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.completes = ArrayDeque(listOf(notUploaded))
        val vm = ready(api)

        choose(vm)
        advanceTimeBy(POLL_LIMIT_MS + 1)
        // Every 2 s from 0 s to 60 s, then it stops.
        assertEquals(31, api.completed.size)
        advanceTimeBy(30_000)
        assertEquals(31, api.completed.size)

        val failed = assertIs<PhotoUpload.Failed>(vm.state.value.upload)
        assertTrue(failed.slow)
        assertEquals("hub.media.not_uploaded", failed.failure.messageKey)
        assertTrue(failed.failure.canRetry)

        api.completes = ArrayDeque(listOf(AuthResult.Ok(media(status = "pending_review"))))
        vm.retry()
        runCurrent()

        assertEquals(PhotoUpload.Done, vm.state.value.upload)
        assertEquals(1, api.started.size, "Check again never starts a second upload")
        assertEquals(1, api.sent.size)
    }

    @Test
    fun `unreadable`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.completes = ArrayDeque(listOf(refused("MEDIA_UNREADABLE", "hub.media.unreadable")))
        val vm = ready(api)

        choose(vm)
        advanceUntilIdle()

        val failed = assertIs<PhotoUpload.Failed>(vm.state.value.upload)
        assertEquals("hub.media.unreadable", failed.failure.messageKey)
        assertFalse(failed.failure.canRetry, "a refusal ends this photo")
        assertEquals(1, api.completed.size, "a refusal ends the poll")
        assertEquals(listOf<String?>(null, null), api.listed, "the list is read again to show the rejected photo")

        vm.retry()
        advanceUntilIdle()
        assertEquals(1, api.completed.size)
        assertEquals(" A class ", vm.state.value.altEn, "the typed text is kept for the next photo")
    }

    @Test
    fun `a file the phone cannot read is refused in the servers words`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        val vm = ready(api)

        choose(vm, png { throw IOException("gone") })
        advanceUntilIdle()

        assertEquals("hub.media.unreadable", assertIs<PhotoUpload.Failed>(vm.state.value.upload).failure.messageKey)
        assertTrue(api.started.isEmpty())
    }

    @Test
    fun `limit reached`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.inits = ArrayDeque(listOf(refused("MEDIA_LIMIT_REACHED", "hub.media.limit_reached")))
        val vm = ready(api, batchId = BATCH)

        choose(vm)
        advanceUntilIdle()

        val failed = assertIs<PhotoUpload.Failed>(vm.state.value.upload)
        assertEquals("hub.media.limit_reached", failed.failure.messageKey)
        assertFalse(failed.failure.canRetry)
        assertEquals(listOf(MediaUploadInit(BATCH, "image/png", 10)), api.started)
        assertTrue(api.sent.isEmpty(), "nothing is posted to the bucket")
        assertEquals(8, vm.state.value.limit, "a batch gallery holds eight")
    }

    @Test
    fun `network failure keeps alt text and offers retry`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.sends = ArrayDeque(listOf(AuthResult.TransportFailure, AuthResult.Ok(Unit)))
        val vm = ready(api)

        choose(vm)
        advanceUntilIdle()

        val failed = assertIs<PhotoUpload.Failed>(vm.state.value.upload)
        assertEquals(HUB_OFFLINE_KEY, failed.failure.messageKey)
        assertTrue(failed.failure.canRetry)
        assertEquals(" A class ", vm.state.value.altEn)
        assertEquals("ক্লাস", vm.state.value.altBn)

        vm.retry()
        advanceUntilIdle()

        assertEquals(PhotoUpload.Done, vm.state.value.upload)
        assertEquals(1, api.started.size, "the same ticket is posted again")
        assertEquals(2, api.sent.size)
    }

    @Test
    fun `a dropped connection on complete is retried by polling, not by uploading`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.completes =
            ArrayDeque(listOf(AuthResult.TransportFailure, AuthResult.Ok(media(status = "pending_review"))))
        val vm = ready(api)

        choose(vm)
        assertTrue(assertIs<PhotoUpload.Failed>(vm.state.value.upload).failure.canRetry)

        vm.retry()
        runCurrent()

        assertEquals(PhotoUpload.Done, vm.state.value.upload)
        assertEquals(1, api.sent.size)
        assertEquals(2, api.completed.size)
    }

    @Test
    fun `a bucket refusal starts the next retry with a fresh ticket`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.sends = ArrayDeque(listOf(AuthResult.Refused(BUCKET_REFUSAL), AuthResult.Ok(Unit)))
        val vm = ready(api)

        choose(vm)
        val failed = assertIs<PhotoUpload.Failed>(vm.state.value.upload)
        assertEquals(UPLOAD_FAILED_KEY, failed.failure.messageKey)
        assertTrue(failed.failure.canRetry)

        vm.retry()
        runCurrent()

        assertEquals(PhotoUpload.Done, vm.state.value.upload)
        assertEquals(2, api.started.size, "an expired or refused ticket is not posted to again")
    }

    @Test
    fun `a failed start offers retry when no answer arrived`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.inits = ArrayDeque(listOf(AuthResult.TransportFailure, AuthResult.Ok(FakeHubMediaApi.TICKET)))
        val vm = ready(api)

        choose(vm)
        assertTrue(assertIs<PhotoUpload.Failed>(vm.state.value.upload).failure.canRetry)

        vm.retry()
        runCurrent()
        assertEquals(PhotoUpload.Done, vm.state.value.upload)
        assertEquals(2, api.started.size)
    }

    @Test
    fun `both alt texts are required before the picker opens`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        val vm = HubMediaViewModel(api, null)
        vm.editAltEn("A class")
        vm.editAltBn("   ")

        assertFalse(vm.startPicking())

        assertEquals("hub.media.alt_invalid", assertIs<PhotoUpload.Failed>(vm.state.value.upload).failure.messageKey)
        assertTrue(api.started.isEmpty())
    }

    @Test
    fun `alt text stops at the servers limit`() {
        val vm = HubMediaViewModel(FakeHubMediaApi(), null)
        vm.editAltEn("x".repeat(ALT_MAX + 5))
        vm.editAltBn("ক".repeat(ALT_MAX + 5))
        assertEquals(ALT_MAX, vm.state.value.altEn.length)
        assertEquals(ALT_MAX, vm.state.value.altBn.length)
    }

    @Test
    fun `a cancelled picker returns to idle`() = runTest(dispatcher) {
        val vm = ready(FakeHubMediaApi())
        choose(vm, photo = null)
        assertEquals(PhotoUpload.Idle, vm.state.value.upload)
    }

    @Test
    fun `the wrong type or a file over 8 MB is refused before any request`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        val vm = ready(api)

        choose(vm, PickedPhoto("image/gif", 10) { ByteArray(10) })
        assertEquals(
            "hub.media.type_not_allowed",
            assertIs<PhotoUpload.Failed>(vm.state.value.upload).failure.messageKey,
        )

        choose(vm, png(size = MAX_UPLOAD_BYTES + 1))
        assertEquals("hub.media.too_large", assertIs<PhotoUpload.Failed>(vm.state.value.upload).failure.messageKey)

        // A size the phone could not tell is measured from the bytes read.
        choose(vm, png(size = null) { ByteArray(MAX_UPLOAD_BYTES.toInt() + 1) })
        advanceUntilIdle()
        assertEquals("hub.media.too_large", assertIs<PhotoUpload.Failed>(vm.state.value.upload).failure.messageKey)
        assertTrue(api.started.isEmpty())
    }

    @Test
    fun `nothing is picked while an upload is in flight`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.completes = ArrayDeque(listOf(notUploaded))
        val vm = ready(api)
        choose(vm)

        assertEquals(PhotoUpload.WaitingReview, vm.state.value.upload)
        assertFalse(vm.startPicking())
        vm.picked(png())
        runCurrent()
        assertEquals(1, api.started.size)
    }

    @Test
    fun `the quota reads from the servers list, twelve for an owner`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.lists = ArrayDeque(listOf(AuthResult.Ok(listOf(media(PHOTO_A, 1), media(PHOTO_B, 2)))))
        val vm = HubMediaViewModel(api, null)
        assertNull(vm.state.value.photos)

        vm.load()
        advanceUntilIdle()

        assertEquals(2, vm.state.value.count)
        assertEquals(12, vm.state.value.limit)
        assertEquals(listOf<String?>(null), api.listed)

        vm.load()
        advanceUntilIdle()
        assertEquals(1, api.listed.size, "a loaded gallery is not read again on re-entry")
    }

    @Test
    fun `a failed read offers retry`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.lists = ArrayDeque(listOf(AuthResult.TransportFailure, AuthResult.Ok(listOf(media()))))
        val vm = HubMediaViewModel(api, BATCH)
        vm.load()
        advanceUntilIdle()
        assertTrue(vm.state.value.loadFailure?.canRetry == true)

        vm.retryLoad()
        advanceUntilIdle()

        assertNull(vm.state.value.loadFailure)
        assertEquals(1, vm.state.value.photos?.size)
        assertEquals(listOf<String?>(BATCH, BATCH), api.listed)
    }

    @Test
    fun `reorder sends ids in order`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.lists = ArrayDeque(listOf(AuthResult.Ok(listOf(media(PHOTO_A, 1), media(PHOTO_B, 2)))))
        api.orders = ArrayDeque(listOf(AuthResult.Ok(listOf(media(PHOTO_B, 1), media(PHOTO_A, 2)))))
        val vm = HubMediaViewModel(api, null)
        vm.load()
        advanceUntilIdle()

        vm.move(1, -1)
        advanceUntilIdle()

        assertEquals(listOf<Pair<String?, List<String>>>(null to listOf(PHOTO_B, PHOTO_A)), api.ordered)
        assertEquals(listOf(PHOTO_B, PHOTO_A), vm.state.value.photos?.map { it.id })

        vm.move(0, -1)
        vm.move(1, 1)
        advanceUntilIdle()
        assertEquals(1, api.ordered.size, "a move past either end sends nothing")
    }

    @Test
    fun `a failed write keeps the gallery and Retry repeats it`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        api.lists = ArrayDeque(listOf(AuthResult.Ok(listOf(media(PHOTO_A, 1), media(PHOTO_B, 2)))))
        api.orders =
            ArrayDeque(
                listOf(AuthResult.TransportFailure, AuthResult.Ok(listOf(media(PHOTO_B, 1), media(PHOTO_A, 2)))),
            )
        val vm = HubMediaViewModel(api, null)
        vm.load()
        advanceUntilIdle()

        vm.move(0, 1)
        advanceUntilIdle()
        assertTrue(vm.state.value.failure?.canRetry == true)
        assertEquals(listOf(PHOTO_A, PHOTO_B), vm.state.value.photos?.map { it.id })

        vm.retryWrite()
        advanceUntilIdle()
        assertNull(vm.state.value.failure)
        assertEquals(listOf(PHOTO_B, PHOTO_A), vm.state.value.photos?.map { it.id })
        assertEquals(2, api.ordered.size)
    }

    @Test
    fun `deletes only after a confirmation`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        val photo = media(PHOTO_A, 1)
        api.lists = ArrayDeque(listOf(AuthResult.Ok(listOf(photo))))
        val vm = HubMediaViewModel(api, null)
        vm.load()
        advanceUntilIdle()

        vm.askDelete(photo)
        assertEquals(photo, vm.state.value.deleting)
        vm.cancelDelete()
        assertNull(vm.state.value.deleting)
        vm.confirmDelete()
        advanceUntilIdle()
        assertTrue(api.deleted.isEmpty())

        vm.askDelete(photo)
        vm.confirmDelete()
        advanceUntilIdle()

        assertEquals(listOf(PHOTO_A), api.deleted)
        assertEquals(emptyList(), vm.state.value.photos)
        assertNull(vm.state.value.deleting)
    }

    @Test
    fun `a read-only gallery takes no writes`() = runTest(dispatcher) {
        val api = FakeHubMediaApi()
        val photo = media(PHOTO_A, 1)
        api.lists = ArrayDeque(listOf(AuthResult.Ok(listOf(photo, media(PHOTO_B, 2)))))
        val vm = HubMediaViewModel(api, null, readOnly = true)
        vm.load()
        advanceUntilIdle()
        vm.editAltEn("A class")
        vm.editAltBn("ক্লাস")

        assertFalse(vm.startPicking())
        vm.move(0, 1)
        vm.askDelete(photo)
        advanceUntilIdle()

        assertEquals("", vm.state.value.altEn)
        assertTrue(api.ordered.isEmpty())
        assertNull(vm.state.value.deleting)
    }

    private companion object {
        val BUCKET_REFUSAL = ErrorEnvelope(ErrorBody("UPLOAD_FAILED", retryable = true, messageKey = UPLOAD_FAILED_KEY))
    }
}
