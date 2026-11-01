package com.shikkhokplus.app.feature.inbox

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** How a payment was decided. */
enum class PaymentOutcome {
    /** Accepted in full. */
    APPROVED,

    /** Accepted for less than was claimed. */
    PARTIAL,

    /** Not accepted. */
    REJECTED,

    /** Not yet decided. */
    PENDING,
}

/** What an item opens to; the teacher's words are carried untouched. */
sealed interface InboxContent {
    /**
     * A notice.
     *
     * @property body The teacher's words
     * @property postedAt When it was posted
     * @property editedAt When it was last edited, if it was
     */
    data class Notice(val body: String, val postedAt: String, val editedAt: String?) : InboxContent

    /**
     * An exam.
     *
     * @property title Its title
     * @property date The day, as `YYYY-MM-DD`
     * @property subjectName The subject
     * @property totalMarks What it is out of
     * @property topics What it covers
     */
    data class Exam(
        val title: String,
        val date: String,
        val subjectName: String,
        val totalMarks: Int,
        val topics: List<String>,
    ) : InboxContent

    /**
     * A payment result.
     *
     * @property period The period, as `YYYY-MM`
     * @property claimed What was claimed
     * @property approved What was accepted, if decided
     * @property outcome How it was decided
     * @property reason The teacher's reason, if given
     */
    data class Payment(
        val period: String,
        val claimed: Money,
        val approved: Money?,
        val outcome: PaymentOutcome,
        val reason: String?,
    ) : InboxContent
}

/**
 * One item, opened.
 *
 * @property kind What it is about
 * @property batchName The batch
 * @property childName Which child, on a guardian's copy
 * @property content What it opens to, if its kind carries any
 */
data class InboxDetail(
    val kind: InboxKind,
    val batchName: String,
    val childName: String?,
    val content: InboxContent?,
)

/** Everything the detail screen renders. */
sealed interface InboxDetailUiState {
    /** A request is in flight. */
    data object Loading : InboxDetailUiState

    /** The source is gone or no longer reachable. */
    data object Unavailable : InboxDetailUiState

    /**
     * Read.
     *
     * @property detail The item
     */
    data class Loaded(val detail: InboxDetail) : InboxDetailUiState

    /**
     * It failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : InboxDetailUiState
}

/**
 * Holds one opened inbox item.
 *
 * @property repository The inbox
 */
class InboxDetailViewModel(
    private val repository: InboxRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<InboxDetailUiState>(InboxDetailUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<InboxDetailUiState> = _state.asStateFlow()

    /**
     * Read one item.
     *
     * @param id The message
     */
    fun load(id: String) {
        _state.value = InboxDetailUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.detail(id)) {
                    is AuthResult.Ok -> InboxMapper.afterDetail(result.value)
                    is AuthResult.Refused -> InboxMapper.detailError(result.envelope)
                    AuthResult.TransportFailure ->
                        InboxDetailUiState.Failed(InboxMapper.OFFLINE_KEY, retryable = true)
                }
        }
    }
}
