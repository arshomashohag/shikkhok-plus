package com.shikkhokplus.app.feature.hubenquiry

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * One request as the owner sees it, with the answer in hand.
 *
 * @property enquiry The server's request
 * @property closing Whether an answer is in flight
 * @property failure Why the last answer failed, or null
 * @property retryOutcome The answer Retry sends again, or null when trying again cannot help
 * @property answered Whether to say the answer was just sent
 */
data class OwnerEnquiryView(
    val enquiry: OwnerEnquiry,
    val closing: Boolean = false,
    val failure: EnquiryFailure? = null,
    val retryOutcome: EnquiryOutcome? = null,
    val answered: Boolean = false,
)

/** What one owner request renders. */
sealed interface OwnerEnquiryUiState {
    /** Waiting for the request. */
    data object Loading : OwnerEnquiryUiState

    /**
     * The request.
     *
     * @property view The request and the answer in hand
     */
    data class Ready(val view: OwnerEnquiryView) : OwnerEnquiryUiState

    /**
     * The read failed in a way trying again can help.
     *
     * @property messageKey Names a string resource
     */
    data class Error(val messageKey: String) : OwnerEnquiryUiState

    /**
     * Join requests are switched off, or the request is gone: the server's
     * sentence, plainly, with no Retry.
     *
     * @property messageKey Names a string resource
     */
    data class Unavailable(val messageKey: String) : OwnerEnquiryUiState
}

/** What the add-student form does once its student is saved [H5]. */
enum class AfterSave {
    /** Stay: the answer is in flight, failed with its Retry showing, or the request is still being read. */
    WAIT,

    /** Close the form: the request is answered, or there is nothing left to answer. */
    LEAVE,
}

/**
 * Holds one join request for its owner: the detail screen, and the
 * add-student form opened from its "Add as student", which answers
 * [EnquiryOutcome.ADDED] once the student is saved.
 *
 * **The server decides; this carries.** The answers offered are exactly
 * `outcomes_allowed`, and a refused answer reads in the server's words,
 * with Retry only when the server or the dropped connection says trying
 * again can help.
 *
 * @property api The network
 * @property enquiryId The request
 */
class OwnerEnquiryViewModel(
    private val api: OwnerEnquiriesApi,
    private val enquiryId: String,
) : ViewModel() {

    private val _state = MutableStateFlow<OwnerEnquiryUiState>(OwnerEnquiryUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<OwnerEnquiryUiState> = _state.asStateFlow()

    private var reading: Job? = null

    private val shown: OwnerEnquiryView? get() = (_state.value as? OwnerEnquiryUiState.Ready)?.view

    /**
     * Read the request. A request already shown is read again quietly, so
     * a return from the add-student form shows the answer it gave; nothing
     * is read while an answer is in flight or a failure with its Retry is
     * showing [TC-8].
     */
    fun load() {
        val view = shown
        if (view != null && (view.closing || view.failure != null)) return
        if (reading?.isActive == true) return
        reading =
            viewModelScope.launch {
                val result = api.read(enquiryId)
                _state.value =
                    when (result) {
                        is AuthResult.Ok -> OwnerEnquiryUiState.Ready(OwnerEnquiryView(result.value))
                        else ->
                            result.enquiryFailure().let {
                                if (it.canRetry) {
                                    OwnerEnquiryUiState.Error(it.messageKey)
                                } else {
                                    OwnerEnquiryUiState.Unavailable(it.messageKey)
                                }
                            }
                    }
            }
    }

    /** Read again after a failure trying again can help. */
    fun retryLoad() {
        if (_state.value !is OwnerEnquiryUiState.Error) return
        _state.value = OwnerEnquiryUiState.Loading
        load()
    }

    /**
     * Answer the request, with one of the answers the server offers.
     *
     * @param outcome The answer
     */
    fun answer(outcome: EnquiryOutcome) {
        val view = shown ?: return
        if (view.closing || outcome !in view.enquiry.offered) return
        // A re-read landing after this would show the request open again and
        // re-enable the answers while this one is in flight.
        reading?.cancel()
        val sending = view.copy(closing = true, failure = null, retryOutcome = null, answered = false)
        _state.value = OwnerEnquiryUiState.Ready(sending)
        viewModelScope.launch {
            val result = api.close(enquiryId, outcome)
            val next =
                when (result) {
                    is AuthResult.Ok -> OwnerEnquiryView(result.value, answered = true)
                    else ->
                        result.enquiryFailure().let {
                            sending.copy(
                                closing = false,
                                failure = it,
                                retryOutcome = outcome.takeIf { _ -> it.canRetry },
                            )
                        }
                }
            _state.value = OwnerEnquiryUiState.Ready(next)
        }
    }

    /**
     * Answer [EnquiryOutcome.ADDED], once the add-student form has saved the
     * student, when the server still offers that answer. A request already
     * answered is left as it is.
     *
     * @return Whether the answer was sent
     */
    fun answerAdded(): Boolean {
        val view = shown ?: return false
        if (view.closing || EnquiryOutcome.ADDED !in view.enquiry.offered) return false
        answer(EnquiryOutcome.ADDED)
        return true
    }

    /**
     * The add-student form's next step once its student is saved: answer
     * [EnquiryOutcome.ADDED] while the server offers it, wait while an
     * answer is in flight or its failure is showing, and leave once the
     * request is answered, or when there is nothing left to answer.
     *
     * **Called again after the form is recreated**, the process included:
     * the form remembers the student was saved, this view model does not,
     * so a fresh read that still offers `added` sends it rather than
     * leaving Save disabled with no way forward.
     *
     * @return What the form does now
     */
    fun afterSave(): AfterSave {
        val view = shown ?: return AfterSave.WAIT
        return when {
            view.answered -> AfterSave.LEAVE
            view.closing || view.failure != null -> AfterSave.WAIT
            answerAdded() -> AfterSave.WAIT
            else -> AfterSave.LEAVE
        }
    }

    /** Send the failed answer again, when that can help. */
    fun retry() {
        shown?.retryOutcome?.let(::answer)
    }

    /** Forget the "answer sent" confirmation. */
    fun dismissNotice() {
        shown?.let { _state.value = OwnerEnquiryUiState.Ready(it.copy(answered = false)) }
    }
}
