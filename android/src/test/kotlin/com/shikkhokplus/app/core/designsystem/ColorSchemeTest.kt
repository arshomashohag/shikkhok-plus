package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Every colour role is one of the design's tokens.
 *
 * **The defect this pins:** roles the scheme never set fell back to
 * Material's purple defaults, and they showed. A stock `Card` read
 * `surfaceContainerHighest` and came out lavender, a selected guardian
 * chip read `secondaryContainer`, and the OTP's wrong-code fill read
 * `errorContainer`. Nothing failed; the screens were just the wrong
 * colour. So this compares each role against M3's own default and
 * fails on any that still matches it.
 */
class ColorSchemeTest {

    /**
     * Every role of a scheme, by name.
     *
     * @param scheme The scheme
     * @return Each role's name and colour
     */
    private fun roles(scheme: ColorScheme): Map<String, Color> =
        mapOf(
            "primary" to scheme.primary,
            "onPrimary" to scheme.onPrimary,
            "primaryContainer" to scheme.primaryContainer,
            "onPrimaryContainer" to scheme.onPrimaryContainer,
            "inversePrimary" to scheme.inversePrimary,
            "secondary" to scheme.secondary,
            "onSecondary" to scheme.onSecondary,
            "secondaryContainer" to scheme.secondaryContainer,
            "onSecondaryContainer" to scheme.onSecondaryContainer,
            "tertiary" to scheme.tertiary,
            "onTertiary" to scheme.onTertiary,
            "tertiaryContainer" to scheme.tertiaryContainer,
            "onTertiaryContainer" to scheme.onTertiaryContainer,
            "background" to scheme.background,
            "onBackground" to scheme.onBackground,
            "surface" to scheme.surface,
            "onSurface" to scheme.onSurface,
            "surfaceVariant" to scheme.surfaceVariant,
            "onSurfaceVariant" to scheme.onSurfaceVariant,
            "inverseSurface" to scheme.inverseSurface,
            "inverseOnSurface" to scheme.inverseOnSurface,
            "error" to scheme.error,
            "onError" to scheme.onError,
            "errorContainer" to scheme.errorContainer,
            "onErrorContainer" to scheme.onErrorContainer,
            "outline" to scheme.outline,
            "outlineVariant" to scheme.outlineVariant,
            "surfaceBright" to scheme.surfaceBright,
            "surfaceDim" to scheme.surfaceDim,
            "surfaceContainer" to scheme.surfaceContainer,
            "surfaceContainerHigh" to scheme.surfaceContainerHigh,
            "surfaceContainerHighest" to scheme.surfaceContainerHighest,
            "surfaceContainerLow" to scheme.surfaceContainerLow,
            "surfaceContainerLowest" to scheme.surfaceContainerLowest,
        )

    /**
     * The roles a scheme leaves at Material's default.
     *
     * `surface`-white and plain black can legitimately coincide with a
     * default, so a role is reported only when its value is one the
     * design never uses.
     *
     * @param ours The app's scheme
     * @param material Material's default scheme of the same brightness
     * @return The names of roles still at the default
     */
    private fun leftAtDefault(ours: ColorScheme, material: ColorScheme): List<String> {
        val defaults = roles(material)
        return roles(ours)
            .filter { (name, colour) -> colour == defaults.getValue(name) && colour !in DESIGN_NEUTRALS }
            .keys
            .toList()
    }

    @Test
    fun `no light role is left at Material's purple default`() {
        assertEquals(emptyList(), leftAtDefault(ShikkhokLightColors, lightColorScheme()))
    }

    @Test
    fun `no dark role is left at Material's purple default`() {
        assertEquals(emptyList(), leftAtDefault(ShikkhokDarkColors, darkColorScheme()))
    }

    @Test
    fun `the roles the audit found wrong are the design's values`() {
        // A stock Card's fill, a selected chip, the error banner and the
        // dark theme's text on a primary button.
        assertEquals(SurfaceContainerHighLight, ShikkhokLightColors.surfaceContainerHighest)
        assertEquals(BlueContainerLight, ShikkhokLightColors.secondaryContainer)
        assertEquals(Color(0xFFFCE3E1), ShikkhokLightColors.errorContainer)
        assertEquals(Color(0xFF6A110C), ShikkhokLightColors.onErrorContainer)
        assertEquals(Color(0xFF2A2F36), ShikkhokLightColors.inverseSurface)
        assertEquals(Color(0xFF0B2A55), ShikkhokDarkColors.onPrimary)
    }

    @Test
    fun `information banners have a token in both themes`() {
        assertTrue(InfoContainerLight != InfoContainerDark)
        assertEquals(InfoContainerLight, ShikkhokLightColors.tertiaryContainer)
        assertEquals(InfoContainerDark, ShikkhokDarkColors.tertiaryContainer)
    }

    private companion object {
        /** White and black, which a default may share with the design. */
        val DESIGN_NEUTRALS = setOf(Color(0xFFFFFFFF), Color(0xFF000000))
    }
}
