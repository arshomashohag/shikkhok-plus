package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider

/**
 * The app's theme. Wraps every screen.
 *
 * **No dynamic colour.** M3's `dynamicColorScheme` would take the
 * palette from the user's wallpaper, which would discard the contrast
 * work in [ShikkhokLightColors] — the 7:1 floor is a decision about
 * reading an amount in sunlight, and a wallpaper cannot know it. It
 * would also let the payment states drift towards each other, and
 * those must stay distinguishable without colour at all.
 *
 * @param darkTheme Whether to use the dark scheme; follows the system
 *   by default
 * @param content The screen
 */
@Composable
fun ShikkhokTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    // The status colours follow the same switch as the scheme, so a
    // screen forced light or dark gets matching chips — which the call
    // sites used to approximate by testing the surface's luminance.
    CompositionLocalProvider(
        LocalStatusColors provides if (darkTheme) DarkStatusColors else LightStatusColors,
    ) {
        MaterialTheme(
            colorScheme = if (darkTheme) ShikkhokDarkColors else ShikkhokLightColors,
            typography = ShikkhokTypography,
            shapes = ShikkhokShapes,
            content = content,
        )
    }
}

/**
 * The guardian's larger type and reach around [content], when [enabled].
 *
 * Applied once, around the whole navigation graph, for the guardian
 * lens: every screen a guardian can reach is a guardian screen, and a
 * scale applied screen by screen would miss the shared ones. Colours
 * and shapes are the surrounding theme's.
 *
 * @param enabled Whether the signed-in lens is the guardian's
 * @param content The screens
 */
@Composable
fun GuardianScale(enabled: Boolean, content: @Composable () -> Unit) {
    if (!enabled) {
        content()
        return
    }
    CompositionLocalProvider(LocalTouchScale provides GuardianTouch) {
        MaterialTheme(
            colorScheme = MaterialTheme.colorScheme,
            typography = GuardianTypography,
            shapes = MaterialTheme.shapes,
            content = content,
        )
    }
}
