package com.shikkhokplus.app.core.designsystem

import android.os.Build
import android.view.HapticFeedbackConstants
import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.platform.LocalView

/**
 * The app's three haptic moments, and nothing else.
 *
 * **Haptics confirm an outcome; they do not decorate a tap.** A button
 * press already has its ripple, and the system keyboard already
 * vibrates on its own keys. What touch cannot otherwise tell a teacher
 * — who is often looking at a student, a notebook or a bKash statement
 * rather than the screen — is that something they did has *landed*:
 *
 * - [confirm]: a payment approval the server accepted;
 * - [reject]: a payment rejection the server accepted;
 * - [tick]: moving on to the next student while entering marks, so a
 *   batch can be marked by rhythm without looking up after each one.
 *
 * All three go through `View.performHapticFeedback`, which honours the
 * person's system setting: someone who turned touch vibration off
 * feels nothing, and no permission is needed.
 */
interface Haptics {
    /** A decision the server accepted, on the positive side. */
    fun confirm()

    /** A decision the server accepted, on the negative side. */
    fun reject()

    /** A small step completed, such as moving to the next row. */
    fun tick()
}

/**
 * The real implementation, on the composition's own view.
 *
 * `CONFIRM` and `REJECT` arrived in API 30; below that the closest
 * long-standing constants stand in, so a budget phone on an older
 * Android still feels the difference between the two.
 */
private class ViewHaptics(private val view: View) : Haptics {
    override fun confirm() {
        view.performHapticFeedback(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                HapticFeedbackConstants.CONFIRM
            } else {
                HapticFeedbackConstants.VIRTUAL_KEY
            },
        )
    }

    override fun reject() {
        view.performHapticFeedback(
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                HapticFeedbackConstants.REJECT
            } else {
                HapticFeedbackConstants.LONG_PRESS
            },
        )
    }

    override fun tick() {
        view.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
    }
}

/**
 * A replacement for tests, which have no motor to observe. Null — the
 * default — means the real one on the current view.
 */
val LocalHaptics = staticCompositionLocalOf<Haptics?> { null }

/**
 * The haptics for this composition.
 *
 * @return The provided replacement, or the real one on this view
 */
@Composable
fun rememberHaptics(): Haptics {
    val provided = LocalHaptics.current
    val view = LocalView.current
    return remember(provided, view) { provided ?: ViewHaptics(view) }
}
