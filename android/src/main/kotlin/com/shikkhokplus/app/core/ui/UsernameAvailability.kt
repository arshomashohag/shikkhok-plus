package com.shikkhokplus.app.core.ui

import com.shikkhokplus.app.core.network.UsernameAvailabilityDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * What the username field's availability hint shows (functional-spec 3.1).
 *
 * **Never a gate.** No state disables submission [FR3.2, FR11.3]: the
 * hint can be stale by the time a form is sent, and the server's answer
 * to the submission is the one that stands. The state machine's
 * `Waiting` is not a state here: it renders as [Idle], the help line, so
 * the hint does not flicker while someone types.
 */
sealed interface AvailabilityState {
    /** Nothing to say yet: the help line. */
    data object Idle : AvailabilityState

    /** A lookup is with the server. */
    data object Checking : AvailabilityState

    /** The server said the name is free. */
    data object Available : AvailabilityState

    /**
     * The server said the name cannot be had, and which string says why.
     *
     * `unavailable` covers taken and held alike [NFR1.3, ADR-007]: there
     * is no state that could tell them apart.
     *
     * @property messageKey An `account.username.*` key
     */
    data class Refused(val messageKey: String) : AvailabilityState

    /** No usable answer: refused, timed out, or unreachable. Submission stays open. */
    data object CouldNotCheck : AvailabilityState
}

/**
 * Turns a lookup's answer into a hint. Pure; the unit under test.
 *
 * Renders only the server's four answers and nothing more [NFR1.3]; an
 * answer this client does not understand is "could not check", never a
 * guess [NFR6.3].
 */
object AvailabilityMapper {
    /** The refusal that means the hourly lookup window is spent [NFR2.1]. */
    const val TOO_MANY_KEY: String = "auth.lookup.too_many"

    /** The key for a name that is taken or held. */
    const val UNAVAILABLE_KEY: String = "account.username.unavailable"

    /** The key for a reserved name. */
    const val RESERVED_KEY: String = "account.username.reserved"

    /**
     * Map one lookup.
     *
     * @param result The repository's answer
     * @return The hint to show
     */
    fun afterLookup(result: AuthResult<UsernameAvailabilityDto>): AvailabilityState =
        when (result) {
            is AuthResult.Ok -> afterAnswer(result.value)
            // A 429 and every other refusal alike: the person may still
            // continue, and the server judges the submission [FR3.2].
            is AuthResult.Refused, AuthResult.TransportFailure -> AvailabilityState.CouldNotCheck
        }

    /**
     * Whether an answer means no further lookup may be sent from this
     * screen: the server's window is spent [NFR2.1].
     *
     * @param result The repository's answer
     * @return True for `429 auth.lookup.too_many`
     */
    fun stopsChecking(result: AuthResult<UsernameAvailabilityDto>): Boolean =
        result is AuthResult.Refused && result.envelope.error.messageKey == TOO_MANY_KEY

    private fun afterAnswer(answer: UsernameAvailabilityDto): AvailabilityState =
        when (answer.status) {
            "available" -> AvailabilityState.Available
            "unavailable" -> AvailabilityState.Refused(UNAVAILABLE_KEY)
            "reserved" -> AvailabilityState.Refused(RESERVED_KEY)
            "invalid" -> answer.messageKey?.let { AvailabilityState.Refused(it) } ?: AvailabilityState.CouldNotCheck
            else -> AvailabilityState.CouldNotCheck
        }
}

/**
 * The live availability check behind one username field [FR3.1; NFR8.1,
 * NFR8.2, NFR8.3, NFR2.1].
 *
 * A plain class owned by a ViewModel, which passes its scope and the
 * lookup it uses (the public one at sign-up and on the replacement
 * step, the authenticated one on the gate and the rename form).
 *
 * **The rules, each of which a test pins:**
 * - a lookup is sent only after [debounceMs] with no edit, and every edit
 *   restarts the wait; an empty field sends nothing;
 * - at most one lookup is in flight: an edit cancels the one outstanding,
 *   so no answer can arrive for a text that has gone (and an answer is
 *   applied only if its text is still the field's, besides);
 * - answers are remembered per text for the screen's life, so retyping a
 *   name sends nothing;
 * - the wait for an answer is bounded by [timeoutMs], outside the
 *   repository call so it changes no other request; no answer in time is
 *   "could not check";
 * - nothing is retried by itself, and after a `429 auth.lookup.too_many`
 *   this instance sends nothing more: the hint says it could not check
 *   and submission stays open.
 *
 * @property scope Where lookups run; the owning ViewModel's
 * @property lookup Asks the server about one trimmed name
 * @property debounceMs The quiet time before a lookup
 * @property timeoutMs The longest wait for an answer
 */
class UsernameAvailabilityChecker(
    private val scope: CoroutineScope,
    private val lookup: suspend (String) -> AuthResult<UsernameAvailabilityDto>,
    private val debounceMs: Long = DEBOUNCE_MS,
    private val timeoutMs: Long = TIMEOUT_MS,
) {
    private val _state = MutableStateFlow<AvailabilityState>(AvailabilityState.Idle)

    /** What the hint shows. */
    val state: StateFlow<AvailabilityState> = _state.asStateFlow()

    // The field's trimmed text, as of the last edit.
    private var current = ""

    // Answers already given, by trimmed text.
    private val answers = mutableMapOf<String, AvailabilityState>()

    // The wait, then the lookup, for the latest text: one job, so
    // cancelling it cancels whichever of the two is under way.
    private var pending: Job? = null

    // Set by a 429: the server's window is spent for this screen.
    private var stopped = false

    /**
     * The field changed.
     *
     * @param text What it holds now, untrimmed
     */
    fun edited(text: String) {
        val trimmed = text.trim()
        current = trimmed
        pending?.cancel()
        pending = null
        _state.value =
            when {
                trimmed.isEmpty() -> AvailabilityState.Idle
                stopped -> AvailabilityState.CouldNotCheck
                else -> AvailabilityState.Idle
            }
        if (trimmed.isEmpty() || stopped) return
        pending =
            scope.launch {
                delay(debounceMs)
                answers[trimmed]?.let {
                    _state.value = it
                    return@launch
                }
                _state.value = AvailabilityState.Checking
                val result = withTimeoutOrNull(timeoutMs) { lookup(trimmed) }
                // **Latest wins**: an answer for a text no longer in the
                // field is dropped, even if cancellation came too late.
                if (trimmed != current) return@launch
                if (result == null) {
                    _state.value = AvailabilityState.CouldNotCheck
                    return@launch
                }
                if (AvailabilityMapper.stopsChecking(result)) stopped = true
                val shown = AvailabilityMapper.afterLookup(result)
                // Only a real answer is remembered; a failure is asked
                // again after the next edit, never by itself.
                if (result is AuthResult.Ok) answers[trimmed] = shown
                _state.value = shown
            }
    }

    /** Defaults the design names (functional-spec W1; performance NFR8.1, NFR8.3). */
    companion object {
        /** The quiet time after the last keystroke before a lookup. */
        const val DEBOUNCE_MS: Long = 500

        /** The longest wait for an answer before "could not check". */
        const val TIMEOUT_MS: Long = 3_000
    }
}
