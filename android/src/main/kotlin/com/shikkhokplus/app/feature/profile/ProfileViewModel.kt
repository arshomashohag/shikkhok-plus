package com.shikkhokplus.app.feature.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.network.DeletionSummaryDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * What the profile screen needs from the network.
 */
interface ProfileRepository {
    /**
     * Read this person's own name and address.
     *
     * @return The profile, a refusal, or a transport failure
     */
    suspend fun profile(): AuthResult<MeDto>

    /**
     * Save an edited name and address.
     *
     * @param selfName The new name, or null to leave it alone
     * @param address The new address, or null to leave it alone
     * @return The updated profile, or why the server refused
     */
    suspend fun save(selfName: String?, address: String?): AuthResult<MeDto>

    /**
     * Delete this account, for good [TC-19].
     *
     * @return Nothing on success, or why the server refused
     */
    suspend fun deleteAccount(): AuthResult<Unit>

    /**
     * Read what stays if this account is deleted.
     *
     * @return Batches, students and money owed; zeros when none
     */
    suspend fun deletionSummary(): AuthResult<DeletionSummaryDto>
}

/**
 * Holds the profile screen's state. Holds no business logic
 * [TC-9, D-31].
 *
 * Every decision is delegated to [ProfileStateMapper].
 */
class ProfileViewModel(
    private val repository: ProfileRepository,
) : ViewModel() {

    private val _state = MutableStateFlow<ProfileUiState>(ProfileUiState.Loading)

    /** What the screen renders. */
    val state: StateFlow<ProfileUiState> = _state.asStateFlow()

    private val _deletion = MutableStateFlow<DeletionState>(DeletionState.Idle)

    private val _footprint = MutableStateFlow<TeacherFootprint?>(null)

    /** What a teacher would leave behind, or null for anyone else. */
    val footprint: StateFlow<TeacherFootprint?> = _footprint.asStateFlow()

    /** Where deleting this account stands. */
    val deletion: StateFlow<DeletionState> = _deletion.asStateFlow()

    /** The number from the last read, for the deletion confirmation. */
    private var phone: String? = null

    private var lastAction: (() -> Unit)? = null

    /** Read the profile. */
    fun load() {
        lastAction = { load() }
        _state.value = ProfileUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.profile()) {
                    is AuthResult.Ok -> {
                        phone = result.value.phone
                        ProfileStateMapper.afterLoad(result.value)
                    }
                    is AuthResult.Refused ->
                        ProfileStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        ProfileStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Open the form, pre-filled with what is stored.
     *
     * **No network call.** Editing is a local state change; a read
     * here would discard anything typed if it landed mid-edit.
     */
    fun edit() {
        val current = _state.value
        val name = when (current) {
            is ProfileUiState.Viewing -> current.selfName
            is ProfileUiState.Saved -> current.selfName
            else -> null
        }
        val address = when (current) {
            is ProfileUiState.Viewing -> current.address
            is ProfileUiState.Saved -> current.address
            else -> null
        }
        _state.value =
            ProfileUiState.Editing(
                selfName = name.orEmpty(),
                address = address.orEmpty(),
            )
    }

    /**
     * Save the edited fields.
     *
     * **A blank field is sent as null, not as an empty string.** Null
     * means "leave it alone" to the server, so clearing a field is
     * deliberately not possible here: the screen has no control that
     * means "remove my address", and inventing one by sending `""`
     * would erase data on a save the person thought was a no-op.
     *
     * @param selfName The edited name
     * @param address The edited address
     */
    fun save(selfName: String, address: String) {
        lastAction = { save(selfName, address) }
        _state.value = ProfileUiState.Saving
        viewModelScope.launch {
            _state.value =
                when (
                    val result =
                        repository.save(
                            selfName = selfName.ifBlank { null },
                            address = address.ifBlank { null },
                        )
                ) {
                    is AuthResult.Ok -> {
                        phone = result.value.phone
                        ProfileStateMapper.afterSave(result.value)
                    }
                    is AuthResult.Refused ->
                        ProfileStateMapper.afterError(result.envelope)
                    AuthResult.TransportFailure ->
                        ProfileStateMapper.afterTransportFailure()
                }
        }
    }

    /**
     * Retry, when the person asks.
     *
     * Never automatic: V1 has no local queue [TC-8, D-9].
     */
    fun retry() {
        lastAction?.invoke()
    }

    /**
     * Open the deletion confirmation, with the number to type back, and
     * read what a teacher would leave behind.
     *
     * The plain confirmation shows until the read answers; a teacher's
     * variant replaces it when the server reports batches. A failed read
     * leaves the plain one, and the deletion itself is unaffected.
     */
    fun startDeletion() {
        _deletion.value = DeletionState.Confirming(phone)
        _footprint.value = null
        viewModelScope.launch {
            _footprint.value =
                (repository.deletionSummary() as? AuthResult.Ok)?.value?.takeIf { it.batchCount > 0 }?.let {
                    TeacherFootprint(it.batchCount, it.studentCount, it.outstanding)
                }
        }
    }

    /** Back out of deleting. */
    fun cancelDeletion() {
        if (_deletion.value != DeletionState.Deleting) _deletion.value = DeletionState.Idle
    }

    /**
     * Delete the account, once the typed number matches [TC-19].
     *
     * Ignored unless confirming (or retrying a failure) and the number
     * matches: the button is disabled otherwise, and refusing again here
     * keeps a stale tap from deleting an account.
     *
     * @param typed What the person typed to confirm
     */
    fun deleteAccount(typed: String) {
        val current = _deletion.value
        val known =
            when (current) {
                is DeletionState.Confirming -> current.phone
                is DeletionState.Failed -> current.phone
                else -> return
            }
        if (!numberMatches(typed, known)) return
        _deletion.value = DeletionState.Deleting
        viewModelScope.launch {
            _deletion.value =
                when (val result = repository.deleteAccount()) {
                    is AuthResult.Ok -> DeletionState.Deleted
                    is AuthResult.Refused ->
                        DeletionState.Failed(
                            phone = known,
                            messageKey = result.envelope.error.messageKey,
                            retryable = result.envelope.error.retryable,
                        )
                    AuthResult.TransportFailure ->
                        DeletionState.Failed(
                            phone = known,
                            messageKey = ProfileStateMapper.OFFLINE_KEY,
                            retryable = true,
                        )
                }
        }
    }
}
