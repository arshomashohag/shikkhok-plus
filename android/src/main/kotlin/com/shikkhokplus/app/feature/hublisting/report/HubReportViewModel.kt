package com.shikkhokplus.app.feature.hublisting.report

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.callDiscardingBody
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.HubFailure
import com.shikkhokplus.app.feature.hublisting.hubFailure
import io.ktor.client.HttpClient
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** The server's limit on a report's note (`HubReportRequest.note`). */
const val NOTE_MAX: Int = 500

/** A UUID in its canonical text form, either case; also read by the join-request link. */
internal val UUID_TEXT = Regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

/**
 * What a hub report link may name: the two listing kinds, a photo on
 * either, and a guardian's review or the teacher's reply to one [H4].
 *
 * @property wire The value the server takes
 */
enum class ReportKind(val wire: String) {
    /** A teacher's or centre's page; the id is the owner's. */
    OWNER_LISTING("owner_listing"),

    /** A batch's page; the id is the batch's. */
    BATCH_LISTING("batch_listing"),

    /** A photo on a public page; the id is the photo's. */
    MEDIA("media"),

    /** A guardian's review; the id is the review's. */
    REVIEW("review"),

    /**
     * The teacher's reply to a review. **The id is the review's**: a review
     * has at most one reply, and the server finds it by its review [T9-e].
     */
    REPLY("reply"),
}

/**
 * Why a page is reported: the server's closed vocabulary
 * (`app/moderation/vocab.py`), in the order a reader weighs them.
 *
 * @property wire The value the server takes
 */
enum class ReportReason(val wire: String) {
    /** It puts a child at risk. */
    CHILD_SAFETY("child_safety"),

    /** It shows personal information. */
    PERSONAL_INFO("personal_info"),

    /** It is abusive or offensive. */
    ABUSIVE("abusive"),

    /** It is fake. */
    FAKE("fake"),

    /** It is misleading. */
    MISLEADING("misleading"),

    /** Something else. */
    OTHER("other"),
}

/**
 * A page a report is about, as the link named it and the server takes it.
 *
 * @property kind Which kind of page, a photo on one, a review or a reply
 * @property id The owner's id for an owner page, the batch's for a batch
 *   page, the photo's for a photo, the review's for a review or its reply
 */
data class ReportTarget(val kind: ReportKind, val id: String)

/**
 * A report link as it arrived: the two query values, unchecked, so that a
 * malformed link still opens the screen and is refused there, in words.
 *
 * @property kind The `kind` query value, if any
 * @property id The `id` query value, if any
 */
data class ReportLink(val kind: String?, val id: String?) {
    /** The page this link names, or null when either half is not one a reader may report. */
    val target: ReportTarget?
        get() {
            val known = ReportKind.entries.firstOrNull { it.wire == kind } ?: return null
            return id?.takeIf { UUID_TEXT.matches(it) }?.let { ReportTarget(known, it) }
        }

    companion object {
        /** The path a hub page's "Report this page" link opens, on the web-app host. */
        const val PATH: String = "/ui/hub-report"

        /**
         * Read an incoming link. Only `https://<host>/ui/hub-report` is a
         * report link: the manifest claims no other, and anything else
         * arriving here (an explicit intent, say) is ignored.
         *
         * @param uri The intent's data, if any
         * @param host The app-link host this build claims
         * @return The link's query values, or null when it is not a report link
         */
        fun from(uri: Uri?, host: String): ReportLink? =
            uri?.takeIf { it.scheme == "https" && it.host == host && it.path == PATH }
                ?.let { ReportLink(it.getQueryParameter("kind"), it.getQueryParameter("id")) }
    }
}

/**
 * A report, as `POST /v1/hub/reports` takes it.
 *
 * @property targetKind One of [ReportKind]'s wire values
 * @property targetId The owner's, the batch's, the photo's or the review's id
 * @property reason One of [ReportReason]'s wire values
 * @property note An optional note; omitted when null
 */
@Serializable
data class HubReportRequest(
    @SerialName("target_kind") val targetKind: String,
    @SerialName("target_id") val targetId: String,
    @SerialName("reason") val reason: String,
    @SerialName("note") val note: String? = null,
)

/** What the report screen needs from the network. */
fun interface HubReportApi {
    /**
     * File a report; nothing about the page changes.
     *
     * @param request The report
     * @return Nothing, a refusal, or a transport failure
     */
    suspend fun file(request: HubReportRequest): AuthResult<Unit>
}

/**
 * Reports over HTTP.
 *
 * @property client The authenticated HTTP client
 */
class HttpHubReportApi(
    private val client: HttpClient,
) : HubReportApi {
    override suspend fun file(request: HubReportRequest): AuthResult<Unit> =
        callDiscardingBody { client.post("/v1/hub/reports") { setBody(request) } }
}

/**
 * The report screen.
 *
 * @property target The page reported, or null when the link was not valid
 * @property reason The chosen reason, or null
 * @property note The note as typed, at most [NOTE_MAX] characters
 * @property sending Whether the report is in flight
 * @property sent Whether the server accepted it
 * @property failure Why the last send failed, or null
 */
data class HubReportState(
    val target: ReportTarget?,
    val reason: ReportReason? = null,
    val note: String = "",
    val sending: Boolean = false,
    val sent: Boolean = false,
    val failure: HubFailure? = null,
) {
    /** Whether Send does anything: a valid target, a reason, and nothing in flight or done. */
    val canSend: Boolean get() = target != null && reason != null && !sending && !sent
}

/**
 * Holds one report about a public hub page, opened from its "Report this
 * page" link. The target is the link's and cannot be changed here; a link
 * that names no valid target is shown as such and never sent. A failed
 * send keeps the reason and the note and offers Retry when the server, or
 * the dropped connection, says it can help [TC-8].
 *
 * @property api The network
 * @param link The link that opened the screen
 */
class HubReportViewModel(
    private val api: HubReportApi,
    link: ReportLink,
) : ViewModel() {

    private val _state = MutableStateFlow(HubReportState(target = link.target))

    /** What the screen renders. */
    val state: StateFlow<HubReportState> = _state.asStateFlow()

    /**
     * Choose a reason.
     *
     * @param reason The reason
     */
    fun pickReason(reason: ReportReason) {
        if (_state.value.sending || _state.value.sent) return
        _state.update { it.copy(reason = reason) }
    }

    /**
     * Change the note; anything past the server's limit is not kept.
     *
     * @param text The note as typed
     */
    fun editNote(text: String) {
        if (_state.value.sending || _state.value.sent) return
        _state.update { it.copy(note = text.take(NOTE_MAX)) }
    }

    /** Send the report, when there is a valid target and a reason. */
    fun send() {
        val s = _state.value
        if (!s.canSend) return
        val target = s.target ?: return
        val reason = s.reason ?: return
        val request = HubReportRequest(target.kind.wire, target.id, reason.wire, s.note.trim().ifEmpty { null })
        _state.update { it.copy(sending = true, failure = null) }
        viewModelScope.launch {
            val result = api.file(request)
            _state.update {
                when (result) {
                    is AuthResult.Ok -> it.copy(sending = false, sent = true)
                    else -> it.copy(sending = false, failure = result.hubFailure())
                }
            }
        }
    }

    /** Send again, after a failure that can be retried. */
    fun retry() {
        if (_state.value.failure?.canRetry == true) send()
    }
}
