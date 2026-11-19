package com.shikkhokplus.app.feature.hubenquiry

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.hublisting.ClassLevel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * The request form as typed.
 *
 * **Consent is a choice, never a default.** [share] is null until the
 * guardian picks one of the two options, and [declared] starts false, so
 * "not chosen" can never be sent.
 *
 * @property target Who would receive the request, and what "share" would share
 * @property name The student's name as typed, at most [STUDENT_NAME_MAX] characters
 * @property level The chosen class, or null
 * @property message The message as typed, at most [ENQUIRY_MESSAGE_MAX] characters
 * @property share Whether to share the contact, or null before the guardian chose
 * @property declared Whether the adult-guardian box is ticked
 * @property failure Why the last send failed, or null
 */
data class EnquiryForm(
    val target: EnquiryTarget,
    val name: String = "",
    val level: ClassLevel? = null,
    val message: String = "",
    val share: Boolean? = null,
    val declared: Boolean = false,
    val failure: EnquiryFailure? = null,
) {
    /** Whether Send does anything: a name, a class, a share choice and the declaration. */
    val canSend: Boolean get() = name.isNotBlank() && level != null && share != null && declared

    // A child's name and a family's words [H5: never logged].
    override fun toString(): String = "EnquiryForm(level=$level, share=$share, declared=$declared, failure=$failure)"
}

/** What the request form renders. */
sealed interface EnquiryFormUiState {
    /** Waiting for the target. */
    data object Loading : EnquiryFormUiState

    /** The link names no owner, or a batch that is not one; nothing is sent. */
    data object Invalid : EnquiryFormUiState

    /**
     * The target cannot be asked: join requests are switched off, or this
     * owner is not taking requests. The server's sentence, with no Retry.
     *
     * @property messageKey Names a string resource
     */
    data class Unavailable(val messageKey: String) : EnquiryFormUiState

    /**
     * The target read failed in a way trying again can help.
     *
     * @property messageKey Names a string resource
     */
    data class Error(val messageKey: String) : EnquiryFormUiState

    /**
     * A request with this owner is already open: no form, the way to it instead.
     *
     * @property target Who it went to
     */
    data class AlreadyOpen(val target: EnquiryTarget) : EnquiryFormUiState

    /**
     * The form, idle.
     *
     * @property form What is shown and typed
     */
    data class Ready(val form: EnquiryForm) : EnquiryFormUiState

    /**
     * The send is in flight; nothing can be changed.
     *
     * @property form What is shown and typed
     */
    data class Sending(val form: EnquiryForm) : EnquiryFormUiState

    /**
     * The server accepted the request.
     *
     * @property target Who it went to
     */
    data class Sent(val target: EnquiryTarget) : EnquiryFormUiState
}

/**
 * Holds one "Ask to join" request, opened from a public page's App Link.
 *
 * **The target is the link's and the server's.** The form first reads it,
 * so the guardian sees who would receive the request, and what "share"
 * would share, before choosing; a request already open shows the way to it
 * instead. A failed send keeps everything typed and offers Retry only when
 * the server, or the dropped connection, says trying again can help [TC-8].
 *
 * @property api The network
 * @param link The link that opened the screen
 */
class EnquiryFormViewModel(
    private val api: EnquirerApi,
    link: EnquiryLink,
) : ViewModel() {

    private val recipient: EnquiryRecipient? = link.recipient

    private val _state =
        MutableStateFlow(if (recipient == null) EnquiryFormUiState.Invalid else EnquiryFormUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<EnquiryFormUiState> = _state.asStateFlow()

    private var reading: Job? = null

    /** The form while it is idle; null otherwise. */
    private val idle: EnquiryForm? get() = (_state.value as? EnquiryFormUiState.Ready)?.form

    /**
     * Read the target. Does nothing once anything but the first load is
     * showing: the route loads on every return to the screen and on
     * recreation, and that must never wipe what was typed, a failure with
     * its Retry, or a send under way [TC-8].
     */
    fun load() {
        val to = recipient ?: return
        if (_state.value != EnquiryFormUiState.Loading || reading?.isActive == true) return
        reading =
            viewModelScope.launch {
                val result = api.target(to.owner, to.batch)
                _state.value =
                    when {
                        result is AuthResult.Ok ->
                            if (result.value.alreadyOpen) {
                                EnquiryFormUiState.AlreadyOpen(result.value)
                            } else {
                                EnquiryFormUiState.Ready(EnquiryForm(result.value))
                            }
                        else -> unreadable(result.enquiryFailure())
                    }
            }
    }

    /** Read the target again after a failure trying again can help. */
    fun retryLoad() {
        if (_state.value !is EnquiryFormUiState.Error) return
        _state.value = EnquiryFormUiState.Loading
        load()
    }

    /**
     * Change the student's name; anything past the server's limit is not kept.
     *
     * @param text The name as typed
     */
    fun editName(text: String) = edit { it.copy(name = text.take(STUDENT_NAME_MAX)) }

    /**
     * Choose the student's class.
     *
     * @param level The class
     */
    fun pickLevel(level: ClassLevel) = edit { it.copy(level = level) }

    /**
     * Change the message; anything past the server's limit is not kept.
     *
     * @param text The message as typed
     */
    fun editMessage(text: String) = edit { it.copy(message = text.take(ENQUIRY_MESSAGE_MAX)) }

    /**
     * Choose whether to share the contact.
     *
     * @param share True to share it, false not to
     */
    fun chooseShare(share: Boolean) = edit { it.copy(share = share) }

    /**
     * Tick or untick the adult-guardian declaration.
     *
     * @param value Whether it is ticked
     */
    fun declare(value: Boolean) = edit { it.copy(declared = value) }

    /** Send the request, once every required choice is made. */
    fun send() {
        val to = recipient ?: return
        val form = idle ?: return
        val level = form.level
        val share = form.share
        if (!form.canSend || level == null || share == null) return
        val sending = form.copy(failure = null)
        _state.value = EnquiryFormUiState.Sending(sending)
        val body =
            EnquiryWrite(
                studentName = form.name.trim(),
                classLevel = level.wire,
                message = form.message.trim().ifEmpty { null },
                batchId = to.batch,
                shareContact = share,
                declaresAdultGuardian = true,
            )
        viewModelScope.launch {
            val result = api.send(to.owner, body)
            _state.value =
                when (result) {
                    is AuthResult.Ok -> EnquiryFormUiState.Sent(form.target)
                    else -> EnquiryFormUiState.Ready(sending.copy(failure = result.enquiryFailure()))
                }
        }
    }

    /** Send again, after a failure that can be retried. */
    fun retry() {
        if (idle?.failure?.canRetry == true) send()
    }

    private fun edit(change: (EnquiryForm) -> EnquiryForm) {
        idle?.let { _state.value = EnquiryFormUiState.Ready(change(it)) }
    }

    /** A failed target read: Retry when that can help, else the server's sentence plainly. */
    private fun unreadable(failure: EnquiryFailure): EnquiryFormUiState =
        if (failure.canRetry) {
            EnquiryFormUiState.Error(failure.messageKey)
        } else {
            EnquiryFormUiState.Unavailable(failure.messageKey)
        }
}
