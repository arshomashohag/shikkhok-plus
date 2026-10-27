package com.shikkhokplus.app.navigation

import com.shikkhokplus.app.core.session.Lens

/**
 * Who is signed in, as the graph needs it.
 *
 * **Three values that only make sense together**, bundled rather than
 * passed loose: the lens decides what is routed, and both callbacks
 * exist to change that same lens. Passing them separately pushed this
 * function past the parameter threshold, and the threshold was right
 * — a reader of nine positional arguments cannot see which three are
 * one concern.
 *
 * @property lens Which lens the person is using, or null when signed
 *   out or holding no seat yet
 * @property onSwitch Returns to the lens picker, or null when this
 *   person holds one lens and has nothing to switch to
 * @property onLensesChanged Re-reads the lens list after an action
 *   that can change it, such as accepting a seat. Quiet by contract:
 *   it must not tear down the screen that triggered it [AC9.4.2]
 */
data class SessionBinding(
    val lens: Lens?,
    val onSwitch: (() -> Unit)?,
    val onLensesChanged: () -> Unit,
)
