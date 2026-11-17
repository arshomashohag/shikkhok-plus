package com.shikkhokplus.app.feature.hublisting

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.callDiscardingBody
import com.shikkhokplus.app.core.session.WORKSPACE_HEADER
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * The three replies to "Did the hub bring you a student?".
 *
 * @property wire The value the server takes
 */
enum class FeedbackAnswer(val wire: String) {
    /** The hub brought a student. */
    YES("yes"),

    /** Not yet. */
    NOT_YET("not_yet"),

    /** The owner cannot tell. */
    NOT_SURE("not_sure"),
}

/**
 * An answer to one of the hub's demand questions.
 *
 * @property day Which question: 60 or 90
 * @property answer `yes`, `not_yet` or `not_sure`
 */
@Serializable
data class HubFeedbackRequest(
    @SerialName("day") val day: Int,
    @SerialName("answer") val answer: String,
)

/** What the demand question needs from the network. */
fun interface HubFeedbackApi {
    /**
     * Answer one question; answering again overwrites.
     *
     * @param ownerId The listing's owner, sent as the workspace so a centre manager answers for the centre
     * @param day Which question: 60 or 90
     * @param answer The reply
     * @return Nothing, a refusal, or a transport failure
     */
    suspend fun answer(ownerId: String, day: Int, answer: FeedbackAnswer): AuthResult<Unit>
}

/**
 * The demand question over HTTP.
 *
 * @property client The authenticated HTTP client
 */
class HttpHubFeedbackApi(
    private val client: HttpClient,
) : HubFeedbackApi {
    override suspend fun answer(ownerId: String, day: Int, answer: FeedbackAnswer): AuthResult<Unit> =
        callDiscardingBody {
            client.post("/v1/hub/feedback") {
                // The question belongs to this owner, whichever workspace is open.
                header(WORKSPACE_HEADER, ownerId)
                setBody(HubFeedbackRequest(day, answer.wire))
            }
        }
}

/**
 * The demand question's screen.
 *
 * @property day Which question: 60 or 90
 * @property saved The answer the server last accepted from this screen, or null
 * @property sending The answer in flight, or null
 * @property failure Why the last answer was not saved, or null
 * @property wanted The answer that failed, for Retry
 */
data class HubFeedbackState(
    val day: Int,
    val saved: FeedbackAnswer? = null,
    val sending: FeedbackAnswer? = null,
    val failure: HubFailure? = null,
    val wanted: FeedbackAnswer? = null,
)

/**
 * Holds one answer to "Did the hub bring you a student?". The highlighted
 * choice is only ever one the server accepted; a failed send leaves it as
 * it was and offers Retry [TC-8].
 *
 * @property api The network
 * @property ownerId The listing's owner, from the inbox item
 * @param day Which question, from the inbox item
 */
class HubFeedbackViewModel(
    private val api: HubFeedbackApi,
    private val ownerId: String,
    day: Int,
) : ViewModel() {

    private val _state = MutableStateFlow(HubFeedbackState(day))

    /** What the screen renders. */
    val state: StateFlow<HubFeedbackState> = _state.asStateFlow()

    /**
     * Send an answer.
     *
     * @param answer The reply
     */
    fun answer(answer: FeedbackAnswer) {
        if (_state.value.sending != null) return
        _state.update { it.copy(sending = answer, failure = null, wanted = answer) }
        viewModelScope.launch {
            val result = api.answer(ownerId, _state.value.day, answer)
            _state.update {
                when (result) {
                    is AuthResult.Ok -> it.copy(saved = answer, sending = null, wanted = null)
                    else -> it.copy(sending = null, failure = result.hubFailure())
                }
            }
        }
    }

    /** Send the answer that last failed again. */
    fun retry() {
        val s = _state.value
        if (s.failure?.canRetry == true) s.wanted?.let(::answer)
    }
}
