package com.shikkhokplus.app.feature.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
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

    private var lastAction: (() -> Unit)? = null

    /** Read the profile. */
    fun load() {
        lastAction = { load() }
        _state.value = ProfileUiState.Loading
        viewModelScope.launch {
            _state.value =
                when (val result = repository.profile()) {
                    is AuthResult.Ok -> ProfileStateMapper.afterLoad(result.value)
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
                    is AuthResult.Ok -> ProfileStateMapper.afterSave(result.value)
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
}
