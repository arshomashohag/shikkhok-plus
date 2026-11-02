package com.shikkhokplus.app.feature.paymentmethods

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.PaymentMethodDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** One entry in the editable service dropdown. */
sealed interface ProviderOption {
    /**
     * A service the server suggests.
     *
     * @property name The service name
     */
    data class Service(val name: String) : ProviderOption

    /**
     * Use exactly what was typed as a new service.
     *
     * @property text The typed text
     */
    data class UseTyped(val text: String) : ProviderOption
}

/** Where saving stands. */
sealed interface MethodEditorStatus {
    /** The form is being filled in. */
    data object Editing : MethodEditorStatus

    /** The write is in flight. */
    data object Saving : MethodEditorStatus

    /** The write succeeded. */
    data object Saved : MethodEditorStatus

    /**
     * The write failed; the form is kept as typed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : MethodEditorStatus
}

/**
 * Everything P2 and P3 render.
 *
 * @property kind Mobile or bank
 * @property provider The mobile service, or the bank's name
 * @property mobileNumber The number as typed
 * @property accountNumber The bank account number
 * @property accountName The account holder
 * @property branchName The branch
 * @property note The optional note for payers
 * @property isEditing Whether this replaces an existing method
 * @property status Where saving stands
 */
data class MethodEditorState(
    val kind: MethodKind = MethodKind.MOBILE,
    val provider: String = "",
    val mobileNumber: String = "",
    val accountNumber: String = "",
    val accountName: String = "",
    val branchName: String = "",
    val note: String = "",
    val isEditing: Boolean = false,
    val status: MethodEditorStatus = MethodEditorStatus.Editing,
) {
    /**
     * Whether every required field has something in it. Whether it is
     * valid is the server's decision.
     */
    val canSave: Boolean
        get() =
            status != MethodEditorStatus.Saving &&
                when (kind) {
                    MethodKind.MOBILE -> provider.isNotBlank() && mobileNumber.isNotBlank()
                    MethodKind.BANK ->
                        provider.isNotBlank() &&
                            accountNumber.isNotBlank() &&
                            accountName.isNotBlank() &&
                            branchName.isNotBlank()
                }
}

/**
 * Holds the add and edit forms. Holds no business logic [TC-9, D-31]:
 * Save is enabled when the required fields are present, and the
 * server decides whether they are right.
 *
 * @property repository The network
 * @property services Mobile service names to suggest
 * @param existing The method being edited, or null to add one
 */
class MethodEditorViewModel(
    private val repository: PaymentMethodsRepository,
    val services: List<String> = DEFAULT_SERVICES,
    private val existing: PaymentMethodDto? = null,
) : ViewModel() {

    private val _state = MutableStateFlow(initialState(existing))

    /** What the form renders. */
    val state: StateFlow<MethodEditorState> = _state.asStateFlow()

    /**
     * Switch between mobile banking and bank.
     *
     * @param kind The kind to show
     */
    fun selectKind(kind: MethodKind) =
        edit { if (kind == this.kind) this else copy(kind = kind, provider = "") }

    /**
     * Set the service or bank name.
     *
     * @param value The text
     */
    fun setProvider(value: String) = edit { copy(provider = value) }

    /**
     * Set the mobile number.
     *
     * @param value The text
     */
    fun setMobileNumber(value: String) = edit { copy(mobileNumber = value) }

    /**
     * Set the bank account number.
     *
     * @param value The text
     */
    fun setAccountNumber(value: String) = edit { copy(accountNumber = value) }

    /**
     * Set the account holder.
     *
     * @param value The text
     */
    fun setAccountName(value: String) = edit { copy(accountName = value) }

    /**
     * Set the branch.
     *
     * @param value The text
     */
    fun setBranchName(value: String) = edit { copy(branchName = value) }

    /**
     * Set the note for payers.
     *
     * @param value The text
     */
    fun setNote(value: String) = edit { copy(note = value) }

    /**
     * The dropdown's entries for what is typed so far.
     *
     * The services containing the typed text, then "Use “X”" unless
     * the text already names a service exactly.
     *
     * @return The entries to show; none on the bank form
     */
    fun providerOptions(): List<ProviderOption> {
        if (_state.value.kind != MethodKind.MOBILE) return emptyList()
        val typed = _state.value.provider.trim()
        val matches = services.filter { it.contains(typed, ignoreCase = true) }
        val exact = services.any { it.equals(typed, ignoreCase = true) }
        val options = matches.map { ProviderOption.Service(it) }
        return if (typed.isEmpty() || exact) options else options + ProviderOption.UseTyped(typed)
    }

    /** Send the form. A failure keeps everything typed. */
    fun save() {
        val current = _state.value
        if (!current.canSave) return
        _state.value = current.copy(status = MethodEditorStatus.Saving)
        val draft = draftOf(current)
        viewModelScope.launch {
            val result =
                if (existing == null) {
                    repository.create(draft)
                } else {
                    repository.update(existing.methodId, draft)
                }
            val status =
                when (result) {
                    is AuthResult.Ok -> MethodEditorStatus.Saved
                    is AuthResult.Refused ->
                        MethodEditorStatus.Failed(
                            result.envelope.error.messageKey,
                            result.envelope.error.retryable,
                        )
                    AuthResult.TransportFailure -> MethodEditorStatus.Failed(OFFLINE_KEY, retryable = true)
                }
            _state.value = _state.value.copy(status = status)
        }
    }

    /** Send the same form again, when the person asks. */
    fun retry() = save()

    private fun edit(change: MethodEditorState.() -> MethodEditorState) {
        _state.value = _state.value.change().copy(status = MethodEditorStatus.Editing)
    }

    private fun draftOf(form: MethodEditorState): PaymentMethodDraft =
        when (form.kind) {
            MethodKind.MOBILE ->
                PaymentMethodDraft(
                    kind = form.kind,
                    provider = form.provider.trim(),
                    mobileNumber = form.mobileNumber.trim(),
                    note = form.note.trim().ifEmpty { null },
                )
            MethodKind.BANK ->
                PaymentMethodDraft(
                    kind = form.kind,
                    provider = form.provider.trim(),
                    accountNumber = form.accountNumber.trim(),
                    accountName = form.accountName.trim(),
                    branchName = form.branchName.trim(),
                    note = form.note.trim().ifEmpty { null },
                )
        }

    private fun initialState(method: PaymentMethodDto?): MethodEditorState =
        if (method == null) {
            MethodEditorState()
        } else {
            MethodEditorState(
                kind = MethodKind.fromWire(method.kind),
                provider = method.provider.orEmpty(),
                mobileNumber = method.mobileNumber.orEmpty(),
                accountNumber = method.accountNumber.orEmpty(),
                accountName = method.accountName.orEmpty(),
                branchName = method.branchName.orEmpty(),
                note = method.note.orEmpty(),
                isEditing = true,
            )
        }

    companion object {
        /**
         * The suggestions when the server supplies none. The teacher's
         * list route carries no service list, so these are the same
         * three the family route sends.
         */
        val DEFAULT_SERVICES: List<String> = listOf("bKash", "Nagad", "Rocket")
    }
}
