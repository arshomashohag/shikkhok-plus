package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

/**
 * The status colours: every colour that means something about money,
 * attendance or a code, in one place, with a light and a dark value.
 *
 * **Why not Material roles.** The payment states are a closed
 * vocabulary with measured contrast, and mapping them onto `tertiary`
 * or `error` would let a theme change move them — `error` in
 * particular is reserved for form errors, and an overdue fee is not a
 * form error. So these stay literal design values, as they always
 * were. What changes is that they are declared ONCE rather than in
 * the five files that used to hard-code them, and that the dark value
 * is chosen by [ShikkhokTheme] rather than guessed per call site from
 * the surface's luminance.
 *
 * **The dark-theme defects this closes.** Each was a light-only literal
 * drawn on a dark surface: Today's "short of the fee" text (#663C00,
 * 1.86:1 on the dark card), the OTP field's confirming border
 * (#0F5427, 2.0:1), and the student hero's caption (#D8E3F7 on the
 * dark theme's light-blue hero, 1.3:1).
 *
 * **Contrast is a test, not a comment.** `StatusColorsContrastTest`
 * computes every pair below in both themes and holds text to the
 * palette's 7:1 floor and borders and swatches to 3:1. The ratios in
 * these comments are what that test measured; if a value changes, the
 * test is what says whether it still holds.
 */
@Immutable
data class StatusColors(
    /** Paid chip and recorded calendar day: the tonal wash. */
    val paidContainer: Color,
    /** Text and icon on [paidContainer]. Light 7.65:1, dark 8.65:1. */
    val onPaidContainer: Color,
    /** Today's calendar day: the one solid green. */
    val successFill: Color,
    /** Text on [successFill]. Light 9.06:1, dark 9.46:1. */
    val onSuccessFill: Color,
    /** Confirming green on a plain surface: a border, never body text. */
    val successInk: Color,
    /** The OTP boxes' fill while a correct code is being checked. */
    val successTint: Color,
    /** Partial chip: the amber wash. */
    val partialContainer: Color,
    /** Text and icon on [partialContainer]. Light 7.90:1, dark 8.45:1. */
    val onPartialContainer: Color,
    /** "Short of the fee" as text on a plain card. Light 9.50:1, dark 10.77:1. */
    val partialInk: Color,
    /** Due chip: no fill, the surface shows through. */
    val dueContainer: Color,
    /** Text on [dueContainer]. Light 12.59:1, dark 12.81:1. */
    val onDueContainer: Color,
    /** Due chip's outline. Light 4.59:1, dark 5.62:1 against the surface. */
    val dueOutline: Color,
    /** Overdue chip: the app's only solid status fill. */
    val overdueFill: Color,
    /** Text on [overdueFill]. Light 7.56:1, dark 7.81:1. */
    val onOverdueFill: Color,
    /** Verifying chip: a faint violet wash under a dashed outline. */
    val verifyingContainer: Color,
    /** Text on [verifyingContainer]. Light 7.46:1, dark 8.96:1. */
    val onVerifyingContainer: Color,
    /** The verifying chip's dashed outline. */
    val verifyingOutline: Color,
    /**
     * The 1–30-days-late swatch on Dues. Not text, so 3:1 against the
     * card: light 3.24:1, dark 4.11:1. The earlier #E8908A was 2.39:1.
     */
    val lateSwatch: Color,
    /** The OTP boxes' fill when the code was wrong. */
    val errorTint: Color,
    /** The caption line on a primary-filled hero. Light 7.31:1, dark 8.33:1. */
    val heroCaption: Color,
)

/** The status colours on a light surface. */
internal val LightStatusColors =
    StatusColors(
        paidContainer = Color(0xFFDCF1E2),
        onPaidContainer = Color(0xFF0F5427),
        successFill = Color(0xFF0F5427),
        onSuccessFill = Color(0xFFFFFFFF),
        successInk = Color(0xFF0F5427),
        successTint = Color(0xFFF2FAF4),
        partialContainer = Color(0xFFFCE8C3),
        onPartialContainer = Color(0xFF663C00),
        partialInk = Color(0xFF663C00),
        dueContainer = Color(0xFFFFFFFF),
        onDueContainer = Color(0xFF2B3440),
        dueOutline = Color(0xFF6E7682),
        overdueFill = Color(0xFFA3201A),
        onOverdueFill = Color(0xFFFFFFFF),
        verifyingContainer = Color(0xFFEFE6FB),
        onVerifyingContainer = Color(0xFF5B2E9E),
        verifyingOutline = Color(0xFF5B2E9E),
        lateSwatch = Color(0xFFDB6F67),
        errorTint = Color(0xFFFFF6F5),
        heroCaption = Color(0xFFEEF3FC),
    )

/**
 * The status colours on a dark surface.
 *
 * `successTint` is the dark surface itself and `errorTint` the dark
 * error container: the light theme's pale fills would glare on a dark
 * page, which is why the OTP field kept its own containers in dark.
 */
internal val DarkStatusColors =
    StatusColors(
        paidContainer = Color(0xFF10301C),
        onPaidContainer = Color(0xFF8FD9A6),
        successFill = Color(0xFF7FD39A),
        onSuccessFill = Color(0xFF08210F),
        successInk = Color(0xFF8FD9A6),
        successTint = SurfaceDark,
        partialContainer = Color(0xFF3A2A0C),
        onPartialContainer = Color(0xFFF5C26B),
        partialInk = Color(0xFFF5C26B),
        dueContainer = SurfaceDark,
        onDueContainer = Color(0xFFD7DCE3),
        dueOutline = OutlineDark,
        overdueFill = Color(0xFFFF7A6E),
        onOverdueFill = Color(0xFF1F0000),
        verifyingContainer = Color(0xFF2A1B45),
        onVerifyingContainer = Color(0xFFD1B8FF),
        verifyingOutline = Color(0xFFD1B8FF),
        lateSwatch = Color(0xFFC9554D),
        errorTint = ErrorContainerDark,
        heroCaption = Color(0xFF0B2A55),
    )

/**
 * The status colours for the current theme. Provided by
 * [ShikkhokTheme]; the light set is only the default for a preview or
 * test that renders without the theme.
 */
val LocalStatusColors = staticCompositionLocalOf { LightStatusColors }

/** The current theme's status colours, read like `MaterialTheme.colorScheme`. */
val MaterialTheme.statusColors: StatusColors
    @Composable
    @ReadOnlyComposable
    get() = LocalStatusColors.current
