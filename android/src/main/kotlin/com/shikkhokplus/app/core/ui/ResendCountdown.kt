package com.shikkhokplus.app.core.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.TextAction
import kotlinx.coroutines.delay

/**
 * "Resend code in 0:58", then the resend action once it reaches zero (O3).
 *
 * **A wait, not a limit.** The server's ceilings decide whether a code
 * is sent; this only stops a second SMS being asked for before the
 * first has had time to arrive. It is a clock, so it lives here rather
 * than in a screen whose composables may not compare values.
 *
 * @param restartKey Restarts the countdown when it changes
 * @param onResend Called from the resend action
 * @param actionModifier Applied to the resend action, for a test tag
 * @param waitModifier Applied to the countdown line, for a test tag
 * @param seconds How long the wait lasts
 */
@Composable
fun ResendCountdown(
    restartKey: Int,
    onResend: () -> Unit,
    actionModifier: Modifier = Modifier,
    waitModifier: Modifier = Modifier,
    seconds: Int = RESEND_WAIT_SECONDS,
) {
    var secondsLeft by remember(restartKey) { mutableIntStateOf(seconds) }
    LaunchedEffect(restartKey) {
        while (secondsLeft > 0) {
            delay(ONE_SECOND_MS)
            secondsLeft--
        }
    }

    if (secondsLeft > 0) {
        val clock = clockOf(secondsLeft)
        Text(
            text = emphasise(stringResource(R.string.auth_resend_in, clock), clock),
            style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Normal),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = waitModifier,
        )
    } else {
        TextAction(
            text = stringResource(R.string.auth_resend),
            onClick = onResend,
            modifier = actionModifier,
        )
    }
}

/**
 * Format a wait as minutes and two-digit seconds, "0:58".
 *
 * @param seconds The seconds left
 * @return The clock text
 */
internal fun clockOf(seconds: Int): String = "%d:%02d".format(seconds / SIXTY, seconds % SIXTY)

/**
 * Bold one part of a sentence, as the board bolds the clock.
 *
 * @param sentence The whole line, in the person's language
 * @param part The part to bold, if the sentence contains it
 * @return The styled line
 */
@Composable
private fun emphasise(sentence: String, part: String): AnnotatedString {
    val at = sentence.indexOf(part)
    val strong = SpanStyle(fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
    return buildAnnotatedString {
        if (at < 0) {
            append(sentence)
        } else {
            append(sentence.substring(0, at))
            withStyle(strong) { append(part) }
            append(sentence.substring(at + part.length))
        }
    }
}

/** How long before a second code may be asked for. */
const val RESEND_WAIT_SECONDS: Int = 60

private const val ONE_SECOND_MS = 1_000L
private const val SIXTY = 60
