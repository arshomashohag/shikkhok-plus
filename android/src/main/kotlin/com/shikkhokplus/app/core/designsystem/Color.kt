package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color

/**
 * The palette, as the design system fixes it.
 *
 * **One blue for actions. Everything else is ink, until money is
 * involved.** Loud colour is spent on exactly two things: the overdue
 * chip, and a solid primary banner when a class is cancelled or moved.
 * Anything else that wants attention gets weight or position instead.
 *
 * **Every text token is 7:1 or better in both themes**, not the 4.5:1
 * AA floor. The reason is the device and the setting, not a standard:
 * direct sun on a budget LCD at 60% brightness removes most of AA's
 * margin, and a teacher marking attendance in a tin-roofed room is the
 * normal case rather than the edge one. Measured ratios are recorded
 * beside each token so a later change cannot quietly drop below it.
 *
 * `outline` at 4.6:1 is the exception and is for borders and icons
 * only. It never carries text.
 *
 * **Dark surfaces are near-black (#0F1215), not pure black.** Black
 * smears while scrolling on cheap OLED panels, and many budget phones
 * are LCD anyway, where it saves nothing. The battery win comes from
 * the dark theme overall.
 */

// Light ---------------------------------------------------------------

/** Action blue. 8.1:1 on surface. */
internal val BluePrimaryLight = Color(0xFF1D4F91)

/** Tonal companion to [BluePrimaryLight]. */
internal val BlueContainerLight = Color(0xFFD8E3F7)

/** Text on [BlueContainerLight]. */
internal val OnBlueContainerLight = Color(0xFF0B2447)

/** Neutral slate. Never decorative. */
internal val SlateSecondaryLight = Color(0xFF4A5668)

/** Form errors only, never a payment state. */
internal val ErrorLight = Color(0xFFA3201A)

/** The page behind every surface. */
internal val BackgroundLight = Color(0xFFF4F6F9)

/** Cards and sheets. */
internal val SurfaceLight = Color(0xFFFFFFFF)

/** One step up from surface, for grouped rows. */
internal val SurfaceContainerLight = Color(0xFFEEF1F5)

/** Two steps up: table headers, pressed rows. */
internal val SurfaceContainerHighLight = Color(0xFFE4E8EE)

/** Primary text. 17.6:1. */
internal val OnSurfaceLight = Color(0xFF15191F)

/** Secondary text. 8.9:1. */
internal val OnSurfaceVariantLight = Color(0xFF434A55)

/** Borders and icons. 4.6:1 — **not for text**. */
internal val OutlineLight = Color(0xFF6E7682)

/** Dividers only. */
internal val OutlineVariantLight = Color(0xFFC9CED6)

// Dark ----------------------------------------------------------------

/** Action blue, dark. 10.3:1. */
internal val BluePrimaryDark = Color(0xFFA9C7FF)

/** Tonal companion, dark. */
internal val BlueContainerDark = Color(0xFF1E3F6E)

/** Text on [BlueContainerDark]. */
internal val OnBlueContainerDark = Color(0xFFD8E3F7)

/** Neutral slate, dark. */
internal val SlateSecondaryDark = Color(0xFFB9C4D6)

/** Form errors only, dark. */
internal val ErrorDark = Color(0xFFFFB4AB)

/** Near-black, deliberately not #000. */
internal val BackgroundDark = Color(0xFF0F1215)

/** Cards and sheets, dark. */
internal val SurfaceDark = Color(0xFF15191E)

/** One step up, dark. */
internal val SurfaceContainerDark = Color(0xFF1C2128)

/** Two steps up, dark. */
internal val SurfaceContainerHighDark = Color(0xFF252B33)

/** Primary text, dark. 14.5:1. */
internal val OnSurfaceDark = Color(0xFFE6E9EE)

/** Secondary text, dark. 9.2:1. */
internal val OnSurfaceVariantDark = Color(0xFFB5BCC7)

/** Borders and icons, dark. 5.6:1 — **not for text**. */
internal val OutlineDark = Color(0xFF8A929E)

/** Dividers only, dark. */
internal val OutlineVariantDark = Color(0xFF343B45)

/**
 * The light scheme.
 *
 * `surfaceVariant` is mapped to the container tone rather than left at
 * M3's default, because the design tells layers apart by surface tone
 * instead of by shadow — there are no elevations to read.
 */
internal val ShikhokLightColors = lightColorScheme(
    primary = BluePrimaryLight,
    onPrimary = SurfaceLight,
    primaryContainer = BlueContainerLight,
    onPrimaryContainer = OnBlueContainerLight,
    secondary = SlateSecondaryLight,
    onSecondary = SurfaceLight,
    error = ErrorLight,
    onError = SurfaceLight,
    background = BackgroundLight,
    onBackground = OnSurfaceLight,
    surface = SurfaceLight,
    onSurface = OnSurfaceLight,
    surfaceVariant = SurfaceContainerLight,
    onSurfaceVariant = OnSurfaceVariantLight,
    surfaceContainer = SurfaceContainerLight,
    surfaceContainerHigh = SurfaceContainerHighLight,
    outline = OutlineLight,
    outlineVariant = OutlineVariantLight,
)

/** The dark scheme. Same roles, same contrast policy. */
internal val ShikhokDarkColors = darkColorScheme(
    primary = BluePrimaryDark,
    onPrimary = Color(0xFF0B2447),
    primaryContainer = BlueContainerDark,
    onPrimaryContainer = OnBlueContainerDark,
    secondary = SlateSecondaryDark,
    onSecondary = Color(0xFF15191E),
    error = ErrorDark,
    onError = Color(0xFF1F0000),
    background = BackgroundDark,
    onBackground = OnSurfaceDark,
    surface = SurfaceDark,
    onSurface = OnSurfaceDark,
    surfaceVariant = SurfaceContainerDark,
    onSurfaceVariant = OnSurfaceVariantDark,
    surfaceContainer = SurfaceContainerDark,
    surfaceContainerHigh = SurfaceContainerHighDark,
    outline = OutlineDark,
    outlineVariant = OutlineVariantDark,
)
