package com.shikkhokplus.app.feature.mfa

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.core.ui.RECOVERY_CODE_MAX
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Holds the two-step verification screen: the status, and whichever
 * step -- turning on, turning off, new recovery codes -- is in progress.
 *
 * Holds no business logic [TC-9, D-31]. What to draw is [MfaMapper]'s;
 * whether a code is right, whether the account may turn it off, and how
 * many recovery codes are left are the server's. Every write needs a
 * connection, nothing retries by itself, and each submit is also the
 * explicit retry after a failure [TC-8, D-9].
 *
 * @property repository The account's two-step verification
 * @property holder Where each status read is shared with More, or null
 */
class MfaViewModel(
    private val repository: MfaRepository,
    private val holder: MfaStatusHolder? = null,
) : ViewModel() {

    private val _state = MutableStateFlow(MfaUiState())

    /** What the screen renders. */
    val state: StateFlow<MfaUiState> = _state.asStateFlow()

    /** Read the status, keeping what is on screen until the answer arrives. */
    fun load() {
        viewModelScope.launch { readStatus() }
    }

    /** Read the status again after a failure, showing the loader meanwhile. */
    fun retry() {
        _state.update { it.copy(status = MfaStatusUiState.Loading) }
        load()
    }

    /**
     * Start turning it on: ask the server for a secret. Also the retry
     * when that request failed.
     */
    fun turnOn() {
        _state.update { it.copy(flow = MfaFlow.Starting()) }
        viewModelScope.launch {
            val result = repository.setup()
            val next = (result as? AuthResult.Ok)?.let { MfaMapper.confirming(it.value) }
            _state.update { it.copy(flow = next ?: MfaFlow.Starting(MfaMapper.failure(result))) }
        }
    }

    /**
     * Type into the step in progress: the code that confirms setup or
     * makes new recovery codes, or the code that turns it off. A stale
     * refusal clears as soon as the person types again.
     *
     * @param text The field as typed
     */
    fun type(text: String) {
        _state.update { ui ->
            val flow =
                when (val current = ui.flow) {
                    is MfaFlow.Confirming -> current.copy(code = text, write = idle(current.write))
                    is MfaFlow.Renewing -> current.copy(code = text, write = idle(current.write))
                    is MfaFlow.TurningOff ->
                        current.copy(input = text.take(RECOVERY_CODE_MAX), write = idle(current.write))
                    else -> current
                }
            ui.copy(flow = flow)
        }
    }

    /** No authenticator app on this phone opened the link; say so. */
    fun noAuthenticatorApp() {
        updateFlow<MfaFlow.Confirming> { it.copy(noAuthenticator = true) }
    }

    /**
     * Finish turning it on with the first code. Also the retry after a
     * failure: the code is still there.
     */
    fun confirm() {
        val step = _state.value.flow as? MfaFlow.Confirming ?: return
        if (!step.canSubmit) return
        updateFlow<MfaFlow.Confirming> { it.copy(write = WriteState.Saving) }
        viewModelScope.launch {
            when (val result = repository.confirm(step.code)) {
                is AuthResult.Ok -> showCodes(result.value.recoveryCodes, renewed = false)
                else -> updateFlow<MfaFlow.Confirming> { it.copy(write = MfaMapper.failure(result)) }
            }
        }
    }

    /** Start turning it off. */
    fun startTurnOff() {
        _state.update { it.copy(flow = MfaFlow.TurningOff()) }
    }

    /** Switch turning it off between an app code and a recovery code. */
    fun toggleRecoveryCode() {
        updateFlow<MfaFlow.TurningOff> { MfaFlow.TurningOff(useRecovery = !it.useRecovery) }
    }

    /**
     * Turn it off with what was typed. Also the retry after a failure.
     * The server's answer is the new status, shown at once.
     */
    fun turnOff() {
        val step = _state.value.flow as? MfaFlow.TurningOff ?: return
        if (!step.canSubmit) return
        updateFlow<MfaFlow.TurningOff> { it.copy(write = WriteState.Saving) }
        val typed = step.input.trim()
        viewModelScope.launch {
            val result =
                repository.disable(
                    code = typed.takeUnless { step.useRecovery },
                    recoveryCode = typed.takeIf { step.useRecovery },
                )
            when (result) {
                is AuthResult.Ok -> {
                    val status = MfaMapper.statusOf(result.value)
                    holder?.publish(status)
                    _state.value = MfaUiState(status = MfaStatusUiState.Loaded(status))
                }
                else -> updateFlow<MfaFlow.TurningOff> { it.copy(write = MfaMapper.failure(result)) }
            }
        }
    }

    /** Start making new recovery codes. */
    fun startNewCodes() {
        _state.update { it.copy(flow = MfaFlow.Renewing()) }
    }

    /** Make new recovery codes with the code typed. Also the retry. */
    fun renewCodes() {
        val step = _state.value.flow as? MfaFlow.Renewing ?: return
        if (!step.canSubmit) return
        updateFlow<MfaFlow.Renewing> { it.copy(write = WriteState.Saving) }
        viewModelScope.launch {
            when (val result = repository.renewRecoveryCodes(step.code)) {
                is AuthResult.Ok -> showCodes(result.value.recoveryCodes, renewed = true)
                else -> updateFlow<MfaFlow.Renewing> { it.copy(write = MfaMapper.failure(result)) }
            }
        }
    }

    /**
     * The person has saved the codes: back to the status page. The codes
     * are dropped here and cannot be shown again.
     */
    fun finishCodes() {
        updateFlow<MfaFlow.Codes> { MfaFlow.None }
    }

    /**
     * Leave the step in progress without finishing it. Recovery codes on
     * screen are left by [finishCodes], never by this.
     */
    fun cancel() {
        _state.update { ui -> if (ui.flow is MfaFlow.Codes) ui else ui.copy(flow = MfaFlow.None) }
    }

    /**
     * Show recovery codes once, and re-read the status beneath them, so
     * the page behind says it is on and counts the new codes.
     *
     * @param codes The codes, in the server's order
     * @param renewed Whether they replace earlier ones
     */
    private suspend fun showCodes(codes: List<String>, renewed: Boolean) {
        _state.update { it.copy(flow = MfaFlow.Codes(codes, renewed)) }
        readStatus()
    }

    /** Read the status and share a successful answer with More. */
    private suspend fun readStatus() {
        val read = MfaMapper.status(repository.status())
        if (read is MfaStatusUiState.Loaded) holder?.publish(read.status)
        _state.update { it.copy(status = read) }
    }

    /**
     * Change the step in progress, only when it is of the given kind:
     * an answer that arrives after the person left the step changes
     * nothing.
     *
     * @param change The new step, from the current one
     */
    private inline fun <reified F : MfaFlow> updateFlow(crossinline change: (F) -> MfaFlow) {
        _state.update { ui -> (ui.flow as? F)?.let { ui.copy(flow = change(it)) } ?: ui }
    }
}

/**
 * The write state once the person types after a failure.
 *
 * @param write The current write state
 * @return Idle in place of a failure, else unchanged
 */
private fun idle(write: WriteState): WriteState = if (write is WriteState.Failed) WriteState.Idle else write
