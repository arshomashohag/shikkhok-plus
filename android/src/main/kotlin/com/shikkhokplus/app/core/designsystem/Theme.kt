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
