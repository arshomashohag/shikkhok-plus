package com.shikkhokplus.app.feature.hublisting

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * One centre membership's name-consent toggle.
 *
 * @property membership The server's row, holding the server's last answer
 * @property busy Whether a write is in flight
 * @property failureKey Message key for the last failed write, or null
 * @property wanted The value that write tried to set, for Retry
 */
data class ConsentRow(
    val membership: CentreMembership,
    val busy: Boolean = false,
    val failureKey: String? = null,
    val wanted: Boolean? = null,
)

/** The caller's accepted centre memberships. */
sealed interface NameConsentBody {
    /** Waiting for the list. */
    data object Loading : NameConsentBody

    /**
     * The memberships, one toggle each.
     *
     * @property rows The server's rows
     */
    data class Loaded(val rows: List<ConsentRow>) : NameConsentBody

    /**
     * The read failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : NameConsentBody
}

/**
 * The name-consent screen.
 *
 * @property body The toggles
 */
data class NameConsentState(val body: NameConsentBody = NameConsentBody.Loading)

/**
 * Holds "show my name on the centre's public listing": one toggle per
 * accepted membership. The box always shows what the server last said; a
 * failed write leaves it there and offers Retry [TC-8].
 *
 * @property api The network
 */
class NameConsentViewModel(
    private val api: NameConsentApi,
) : ViewModel() {

    private val _state = MutableStateFlow(NameConsentState())

    /** What the screen renders. */
    val state: StateFlow<NameConsentState> = _state.asStateFlow()

    /** Read the memberships; does nothing once they are showing, so re-entry keeps a failed toggle. */
    fun load() {
        if (_state.value.body is NameConsentBody.Loaded) return
        viewModelScope.launch {
            val result = api.centreMemberships()
            _state.update {
                when (result) {
                    is AuthResult.Ok -> NameConsentState(NameConsentBody.Loaded(result.value.map(::ConsentRow)))
                    else ->
                        result.hubFailure()
                            ?.let { f -> NameConsentState(NameConsentBody.Failed(f.messageKey, f.canRetry)) }
                            ?: it
                }
            }
        }
    }

    /** Read the list again after a failure. */
    fun retryLoad() {
        _state.update { NameConsentState() }
        load()
    }

    /**
     * Ask the server to name, or stop naming, the member.
     *
     * @param centreId The centre
     * @param consent The wanted choice
     */
    fun set(centreId: String, consent: Boolean) {
        if (rowOf(centreId)?.busy != false) return
        update(centreId) { it.copy(busy = true, failureKey = null, wanted = consent) }
        viewModelScope.launch {
            val result = api.setNameConsent(centreId, consent)
            update(centreId) { row ->
                when (result) {
                    is AuthResult.Ok ->
                        row.copy(
                            membership = row.membership.copy(publicNameConsent = consent),
                            busy = false,
                            wanted = null,
                        )
                    else -> row.copy(busy = false, failureKey = result.hubFailure()?.messageKey)
                }
            }
        }
    }

    /**
     * Send the choice that last failed again.
     *
     * @param centreId The centre
     */
    fun retry(centreId: String) {
        rowOf(centreId)?.wanted?.let { set(centreId, it) }
    }

    private fun rowOf(centreId: String): ConsentRow? =
        (_state.value.body as? NameConsentBody.Loaded)?.rows?.firstOrNull { it.membership.centreId == centreId }

    private fun update(centreId: String, change: (ConsentRow) -> ConsentRow) =
        _state.update { s ->
            val body = s.body as? NameConsentBody.Loaded ?: return@update s
            s.copy(
                body = body.copy(rows = body.rows.map { if (it.membership.centreId == centreId) change(it) else it }),
            )
        }
}
