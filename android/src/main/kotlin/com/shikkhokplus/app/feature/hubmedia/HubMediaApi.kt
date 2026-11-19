package com.shikkhokplus.app.feature.hubmedia

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.call
import com.shikkhokplus.app.core.network.callDiscardingBody
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.request.delete
import io.ktor.client.request.forms.submitFormWithBinaryData
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.put
import io.ktor.client.request.setBody
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.content.PartData
import io.ktor.http.isSuccess
import io.ktor.utils.io.core.ByteReadPacket
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The client-side key for a file the bucket refused. The server never
 * sends it: the bucket answers in XML, outside the error envelope.
 */
const val UPLOAD_FAILED_KEY: String = "hub.media.upload_failed"

/**
 * One of the owner's photos, as `MediaResponse` in `app/schemas/media.py`.
 *
 * @property id The photo
 * @property batchId The batch it is for; null for the owner's own page
 * @property status Where it is in upload and review, the server's word
 * @property altEn English alt text
 * @property altBn Bangla alt text
 * @property position Its place in its gallery
 * @property width The decoded width in pixels
 * @property height The decoded height in pixels
 * @property rejectionCode Why it was rejected, if it was
 * @property thumbUrl An absolute 320-pixel preview, or null
 */
@Serializable
data class MediaResponse(
    @SerialName("id") val id: String,
    @SerialName("batch_id") val batchId: String? = null,
    @SerialName("status") val status: String,
    @SerialName("alt_en") val altEn: String? = null,
    @SerialName("alt_bn") val altBn: String? = null,
    @SerialName("position") val position: Int,
    @SerialName("width") val width: Int? = null,
    @SerialName("height") val height: Int? = null,
    @SerialName("rejection_code") val rejectionCode: String? = null,
    @SerialName("thumb_url") val thumbUrl: String? = null,
)

/**
 * Start an upload. The server checks the type and size; a null batch is
 * omitted, which the server reads as the owner's own page.
 *
 * @property batchId The batch, or null
 * @property contentType `image/jpeg`, `image/png` or `image/webp`
 * @property byteSize The file's size in bytes
 */
@Serializable
data class MediaUploadInit(
    @SerialName("batch_id") val batchId: String? = null,
    @SerialName("content_type") val contentType: String,
    @SerialName("byte_size") val byteSize: Long,
)

/**
 * What the file is posted to: the bucket's URL and the signed form.
 *
 * @property mediaId The photo the upload is for
 * @property url The POST target
 * @property fields The form fields, in the order they must be sent, before the file
 * @property expiresAt When the signature stops being accepted
 */
@Serializable
data class MediaUploadTicket(
    @SerialName("media_id") val mediaId: String,
    @SerialName("url") val url: String,
    @SerialName("fields") val fields: Map<String, String>,
    @SerialName("expires_at") val expiresAt: String,
)

/**
 * Submit an uploaded photo for review.
 *
 * @property altEn English alt text
 * @property altBn Bangla alt text
 */
@Serializable
data class MediaComplete(
    @SerialName("alt_en") val altEn: String,
    @SerialName("alt_bn") val altBn: String,
)

/**
 * Put one gallery in order.
 *
 * @property batchId The batch, or null (omitted) for the owner's own gallery
 * @property ids The photos, first to last
 */
@Serializable
data class MediaOrder(
    @SerialName("batch_id") val batchId: String? = null,
    @SerialName("ids") val ids: List<String>,
)

/** What the photo editor needs from the network and the bucket. */
interface HubMediaApi {
    /**
     * List one gallery.
     *
     * @param batchId The batch, or null for the owner's own
     * @return The photos in gallery order, a refusal, or a transport failure
     */
    suspend fun list(batchId: String?): AuthResult<List<MediaResponse>>

    /**
     * Start an upload and have it signed.
     *
     * @param body The declared type, size and batch
     * @return The ticket, a refusal, or a transport failure
     */
    suspend fun startUpload(body: MediaUploadInit): AuthResult<MediaUploadTicket>

    /**
     * Post the file to the bucket with the ticket's form.
     *
     * @param ticket The signed form
     * @param contentType The file's type
     * @param bytes The file
     * @return Nothing; a refusal keyed [UPLOAD_FAILED_KEY] when the bucket
     *   answered with an error; or a transport failure
     */
    suspend fun send(ticket: MediaUploadTicket, contentType: String, bytes: ByteArray): AuthResult<Unit>

    /**
     * Submit the uploaded photo for review; safe to repeat while polling.
     *
     * @param mediaId The photo
     * @param body Both alt texts
     * @return The photo, a refusal (`MEDIA_NOT_UPLOADED` while the file is
     *   still being read), or a transport failure
     */
    suspend fun complete(mediaId: String, body: MediaComplete): AuthResult<MediaResponse>

    /**
     * Put a gallery in order.
     *
     * @param batchId The batch, or null for the owner's own
     * @param ids The photos, first to last
     * @return The gallery in its new order, a refusal, or a transport failure
     */
    suspend fun order(batchId: String?, ids: List<String>): AuthResult<List<MediaResponse>>

    /**
     * Withdraw a photo; its stored files are deleted.
     *
     * @param mediaId The photo
     * @return Nothing, a refusal, or a transport failure
     */
    suspend fun delete(mediaId: String): AuthResult<Unit>
}

/**
 * The HTTP client for the bucket, and only the bucket.
 *
 * **Separate from the app's client on purpose.** That one adds the
 * session's bearer token, the workspace and the platform headers to every
 * request; the bucket must never be sent the session token, and the
 * presigned form is the whole of its authorisation. This client has no
 * plugin, no default header and no base URL.
 */
object BucketClient {

    /** The one bucket client the app uses, made on first upload. */
    val shared: HttpClient by lazy { build(OkHttp.create()) }

    /**
     * Build a bucket client on an engine.
     *
     * @param engine The engine; a test passes a mock
     * @return A client that adds nothing to a request
     */
    fun build(engine: HttpClientEngine): HttpClient = HttpClient(engine) { expectSuccess = false }
}

/**
 * The photo editor's network, over HTTP.
 *
 * @property client The authenticated API client
 * @property bucket The bare client the file is posted with; see [BucketClient]
 */
class HttpHubMediaApi(
    private val client: HttpClient,
    private val bucket: HttpClient,
) : HubMediaApi {

    override suspend fun list(batchId: String?): AuthResult<List<MediaResponse>> =
        call { client.get("/v1/hub/media") { parameter("batch_id", batchId) } }

    override suspend fun startUpload(body: MediaUploadInit): AuthResult<MediaUploadTicket> =
        call { client.post("/v1/hub/media/uploads") { setBody(body) } }

    override suspend fun send(ticket: MediaUploadTicket, contentType: String, bytes: ByteArray): AuthResult<Unit> =
        try {
            val response = bucket.submitFormWithBinaryData(ticket.url, bucketForm(ticket, contentType, bytes))
            if (response.status.isSuccess()) AuthResult.Ok(Unit) else AuthResult.Refused(BUCKET_REFUSED)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            // No answer from the bucket at all.
            AuthResult.TransportFailure
        }

    override suspend fun complete(mediaId: String, body: MediaComplete): AuthResult<MediaResponse> =
        call { client.post("/v1/hub/media/$mediaId/complete") { setBody(body) } }

    override suspend fun order(batchId: String?, ids: List<String>): AuthResult<List<MediaResponse>> =
        call { client.put("/v1/hub/media/order") { setBody(MediaOrder(batchId, ids)) } }

    override suspend fun delete(mediaId: String): AuthResult<Unit> =
        callDiscardingBody { client.delete("/v1/hub/media/$mediaId") }

    private companion object {
        /**
         * The presigned form: the signed fields first, in the server's order,
         * and the file last.
         *
         * **Every part names itself with a quoted string**, built here rather
         * than by Ktor's `formData`, which writes a name unquoted when it
         * needs no escaping (`form-data; name=file`). RFC 7578 gives the
         * name as a quoted-string, and S3's browser-POST parser is
         * documented only against that form.
         *
         * @param ticket The signed form
         * @param contentType The file's type
         * @param bytes The file
         * @return The parts, in the order they are sent
         */
        fun bucketForm(ticket: MediaUploadTicket, contentType: String, bytes: ByteArray): List<PartData> {
            val fields =
                ticket.fields.map { (name, value) ->
                    PartData.FormItem(value, {}, disposition("form-data; name=${quoted(name)}"))
                }
            val file =
                PartData.BinaryItem(
                    { ByteReadPacket(bytes) },
                    {},
                    Headers.build {
                        append(HttpHeaders.ContentDisposition, "form-data; name=\"file\"; filename=\"photo\"")
                        append(HttpHeaders.ContentType, contentType)
                    },
                )
            return fields + file
        }

        private fun disposition(value: String): Headers =
            Headers.build { append(HttpHeaders.ContentDisposition, value) }

        /** [text] as an RFC 7578 quoted-string: a quote or a backslash is escaped. */
        private fun quoted(text: String): String = "\"" + text.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

        /**
         * The bucket refused the form (an expired signature, a file the
         * policy does not admit). Retryable: the retry asks for a new ticket.
         */
        val BUCKET_REFUSED =
            ErrorEnvelope(ErrorBody(code = "UPLOAD_FAILED", retryable = true, messageKey = UPLOAD_FAILED_KEY))
    }
}
