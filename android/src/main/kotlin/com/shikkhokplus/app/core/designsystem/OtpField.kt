package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/** How many digits an OTP carries. */
const val OTP_LENGTH: Int = 6

/**
 * Which way the six boxes should read right now.
 */
enum class OtpFieldState {
    /** Being typed, or waiting for the first digit. */
    EDITING,

    /** All six present and being checked. */
    CHECKING,

    /** The server refused the code. */
    WRONG,
}

/**
 * Six boxes for a six-digit code.
 *
 * **It verifies itself on the sixth digit; there is no button.** That
 * is the design's call and it is the right one here: the code is
 * exactly six digits, so the moment the sixth arrives there is nothing
 * left to decide, and a button would be one more tap between a teacher
 * and their classes. It also makes the SMS Retriever path seamless —
 * Android fills all six at once and the check starts without anyone
 * touching the screen.
 *
 * **One real text field underneath, six boxes drawn over it.** Six
 * separate fields would each need focus management, backspace handling
 * and their own autofill behaviour, and SMS autofill would fill only
 * the first. A single field keeps the platform's keyboard, selection
 * and autofill intact, and the boxes are presentation.
 *
 * @param code The digits entered so far
 * @param onCodeChange Called with the new value, already filtered to
 *   digits and capped at [OTP_LENGTH]
 * @param onComplete Called once when the sixth digit arrives
 * @param state How the boxes should read
 * @param modifier The layout modifier
 * @param enabled Whether typing is accepted; false while checking, so
 *   a seventh keystroke cannot race the request
 */
@Composable
fun OtpField(
    code: String,
    onCodeChange: (String) -> Unit,
    onComplete: () -> Unit,
    state: OtpFieldState,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current

    // **Focus AND an explicit show.** Reported from a device: once the
    // keyboard was dismissed it never came back. Dismissing it leaves
    // the hidden field focused, and asking an already-focused field for
    // focus changes nothing, so the keypad stayed down and no code
    // could be typed. Showing the keyboard outright does not depend on
    // focus having moved.
    val summonKeyboard = {
        runCatching { focus.requestFocus() }
        keyboard?.show()
    }

    Box(modifier) {
        BasicTextField(
            value = code,
            onValueChange = { raw ->
                if (!enabled) return@BasicTextField
                // Accepts Bengali digits, because a teacher reading the
                // code off an SMS may be on a Bangla keyboard.
                val digits = raw
                    .mapNotNull { c ->
                        when {
                            c.isDigit() -> c
                            c in '০'..'৯' -> '0' + (c - '০')
                            else -> null
                        }
                    }
                    .take(OTP_LENGTH)
                    .joinToString("")
                if (digits != code) {
                    onCodeChange(digits)
                    if (digits.length == OTP_LENGTH) onComplete()
                }
            },
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.NumberPassword,
            ),
            enabled = enabled,
            singleLine = true,
            modifier = Modifier
                // The field carries the test tag and the accessibility
                // label: it is the thing that actually holds the value,
                // so `performTextInput` and a screen reader both reach
                // the real input rather than a decoration.
                .testTag(TAG_OTP_FIELD)
                .focusRequester(focus)
                .size(1.dp),
            decorationBox = { _ ->
                // Drawn by the boxes below, not by the field itself.
            },
        )

        // **Tapping any box clears all six after a wrong code** (O3), so
        // the person types the new attempt into empty boxes rather than
        // deleting six digits one by one. Otherwise a tap only brings
        // the keyboard back, which a dismissed keyboard otherwise hides.
        Row(
            Modifier
                .fillMaxWidth()
                .clickable(enabled = enabled, onClickLabel = null) {
                    if (state == OtpFieldState.WRONG) onCodeChange("")
                    summonKeyboard()
                },
            horizontalArrangement = Arrangement.spacedBy(Spacing.tight),
        ) {
            repeat(OTP_LENGTH) { index ->
                OtpBox(
                    digit = code.getOrNull(index)?.toString() ?: "",
                    focused = state == OtpFieldState.EDITING && index == code.length,
                    state = state,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }

    // Keyed on `enabled`, not Unit: the field is disabled while a code
    // is checked, which drops its focus, so a refused code would
    // otherwise leave the person with no keyboard to type the next one.
    LaunchedEffect(enabled) { if (enabled) summonKeyboard() }
}

/**
 * One box.
 *
 * @param digit The digit shown, or empty
 * @param focused Whether the caret is conceptually here
 * @param state How the field as a whole reads
 * @param modifier The layout modifier
 */
@Composable
private fun OtpBox(
    digit: String,
    focused: Boolean,
    state: OtpFieldState,
    modifier: Modifier = Modifier,
) {
    val scheme = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(10.dp)

    // Two cues, not one: the border colour AND the fill change, so the
    // wrong-code state is not carried by hue alone.
    val border = when {
        state == OtpFieldState.WRONG -> scheme.error
        state == OtpFieldState.CHECKING -> OtpOk
        focused -> scheme.primary
        else -> scheme.outlineVariant
    }
    // The board's pale fills are drawn on a white page; on a dark one
    // they would glare, so the dark theme keeps its own containers.
    val light = scheme.surface.luminance() > HALF
    val fill = when (state) {
        OtpFieldState.WRONG -> if (light) OtpWrongFill else scheme.errorContainer
        OtpFieldState.CHECKING -> if (light) OtpOkFill else scheme.surface
        OtpFieldState.EDITING -> scheme.surface
    }
    val width = if (state == OtpFieldState.EDITING && !focused) 1.5.dp else 2.dp

    Box(
        modifier
            .height(60.dp)
            .background(fill, shape)
            .border(width, border, shape)
            .semantics { contentDescription = digit.ifEmpty { "empty" } },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = digit,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = scheme.onSurface,
            textAlign = TextAlign.Center,
        )
    }
}

/** The confirming green from the design's OTP artboard. */
private val OtpOk = Color(0xFF0F5427)

/** The checking boxes' fill on the O3 board. */
private val OtpOkFill = Color(0xFFF2FAF4)

/** The wrong-code boxes' fill on the O3 board. */
private val OtpWrongFill = Color(0xFFFFF6F5)

/** Above this luminance a surface is a light theme's. */
private const val HALF = 0.5f

/** Stable test identifier for the code input. Not user-visible text. */
const val TAG_OTP_FIELD: String = "auth_code_field"
