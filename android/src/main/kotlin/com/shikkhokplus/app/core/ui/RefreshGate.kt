package com.shikkhokplus.app.core.ui

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * One pull-to-refresh at a time, and the flag its spinner shows.
 *
 * **A refresh is not a load.** `load()` replaces the screen with its
 * skeleton; a refresh keeps what is on screen and swaps in the answer
 * when it arrives, so a teacher pulling down to see whether a bKash
 * payment has landed never watches the list disappear. The answer
 * replaces the state whatever it is, including a failure: a refresh
 * that failed silently behind stale content would be the app claiming
 * a freshness it does not have.
 *
 * **One in flight.** A second pull while the first is still waiting
 * is dropped rather than queued, so two answers can never land out of
 * order and leave the older one on screen.
 *
 * Always started by the person pulling — never automatic, for the
 * same reason `retry()` is not [TC-8, D-9].
 */
class RefreshGate {
    private val _refreshing = MutableStateFlow(false)

    /** Whether a refresh is in flight; drives the pull indicator. */
    val refreshing: StateFlow<Boolean> = _refreshing.asStateFlow()

    /**
     * Run [block] in [scope] unless a refresh is already in flight.
     *
     * The flag clears when the job completes however it completes —
     * normally, by failure, or cancelled before it ever started — so a
     * refresh cannot leave the spinner running. `invokeOnCompletion`
     * rather than `finally` for that last case: a job cancelled before
     * it starts never enters its body.
     *
     * @param scope The ViewModel's scope
     * @param block The read, which sets the screen's state itself
     * @return Whether this call started a refresh
     */
    fun run(scope: CoroutineScope, block: suspend () -> Unit): Boolean {
        if (!_refreshing.compareAndSet(expect = false, update = true)) return false
        scope.launch { block() }.invokeOnCompletion { _refreshing.value = false }
        return true
    }
}
