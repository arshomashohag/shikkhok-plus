package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * The design's buttons (Components.dc.html, "Buttons").
 *
 * **One place for heights, pills and disabled colours**, because every
 * screen used raw M3 buttons: 40dp tall with 14sp text, where the design
 * draws a 56dp pill at 16sp for the main action and a 48dp pill at 15sp
 * for the rest, and greys a disabled button to `#E4E8EE` with `#6E7682`
 * text rather than M3's translucent onSurface.
 */

/** The main action's text: 16/26 SemiBold. */
private val LargeButtonText: TextStyle
    @Composable get() =
        MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold)

/** A secondary action's text: 15/24 SemiBold. */
private val ButtonText: TextStyle
    @Composable get() =
        MaterialTheme.typography.bodyMedium.copy(
            fontSize = 15.sp,
            lineHeight = 24.sp,
            fontWeight = FontWeight.SemiBold,
        )

/** Side padding inside a pill. */
private val PillPadding = PaddingValues(horizontal = 20.dp)

/**
 * The screen's main action: a 56dp filled pill.
 *
 * @param text The label
 * @param onClick Called when tapped
 * @param modifier The layout modifier
 * @param enabled Whether it can be tapped
 * @param leading Drawn before the label, such as a spinner
 * @param compact The 48dp size the boards use for actions inside a
 *   card (T4), rather than a screen's own 56dp main action
 */
@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    leading: @Composable RowScope.() -> Unit = {},
    compact: Boolean = false,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        contentPadding = PillPadding,
        colors =
            ButtonDefaults.buttonColors(
                disabledContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                disabledContentColor = MaterialTheme.colorScheme.outline,
            ),
        modifier = modifier.heightIn(min = if (compact) Reach.touch else Reach.moneyButton),
    ) {
        leading()
        Text(text, style = if (compact) ButtonText else LargeButtonText)
    }
}

/**
 * A secondary action: a 48dp pill with a 1.5dp outline.
 *
 * @param text The label
 * @param onClick Called when tapped
 * @param modifier The layout modifier
 * @param enabled Whether it can be tapped
 */
@Composable
fun SecondaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        contentPadding = PillPadding,
        border = BorderStroke(1.5.dp, MaterialTheme.colorScheme.outline),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurface),
        modifier = modifier.heightIn(min = Reach.touch),
    ) {
        Text(text, style = ButtonText)
    }
}

/**
 * A softer action beside a primary one, such as "Partial" (T4) or
 * "Enter marks" (T7): a 48dp tonal pill.
 *
 * @param text The label
 * @param onClick Called when tapped
 * @param modifier The layout modifier
 * @param enabled Whether it can be tapped
 */
@Composable
fun TonalButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    FilledTonalButton(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        contentPadding = PillPadding,
        colors =
            ButtonDefaults.filledTonalButtonColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer,
                contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
            ),
        modifier = modifier.heightIn(min = Reach.touch),
    ) {
        Text(text, style = ButtonText)
    }
}

/**
 * An action that removes or deletes: outlined in the error colour, or
 * filled when it is the confirming step.
 *
 * @param text The label
 * @param onClick Called when tapped
 * @param modifier The layout modifier
 * @param enabled Whether it can be tapped
 * @param filled The confirming step, drawn solid
 */
@Composable
fun DestructiveButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    filled: Boolean = false,
) {
    val error = MaterialTheme.colorScheme.error
    if (filled) {
        Button(
            onClick = onClick,
            enabled = enabled,
            shape = CircleShape,
            contentPadding = PillPadding,
            colors =
                ButtonDefaults.buttonColors(
                    containerColor = error,
                    contentColor = MaterialTheme.colorScheme.onError,
                    disabledContainerColor = error.copy(alpha = DISABLED_DESTRUCTIVE),
                    disabledContentColor = MaterialTheme.colorScheme.onError,
                ),
            modifier = modifier.heightIn(min = Reach.moneyButton),
        ) {
            Text(text, style = LargeButtonText)
        }
    } else {
        OutlinedButton(
            onClick = onClick,
            enabled = enabled,
            shape = CircleShape,
            contentPadding = PillPadding,
            border = BorderStroke(1.5.dp, error),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = error),
            modifier = modifier.heightIn(min = Reach.touch),
        ) {
            Text(text, style = ButtonText)
        }
    }
}

/**
 * A text-only action such as "Change" or "See all": primary colour,
 * 48dp tall so it is still easy to hit.
 *
 * @param text The label
 * @param onClick Called when tapped
 * @param modifier The layout modifier
 * @param enabled Whether it can be tapped
 */
@Composable
fun TextAction(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    TextButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.heightIn(min = Reach.touch),
    ) {
        Text(text, style = ButtonText.copy(fontWeight = FontWeight.Bold))
    }
}

/** The design greys a disabled destructive button by fading its red. */
private const val DISABLED_DESTRUCTIVE = 0.45f

/**
 * A grey question followed by a bold link, centred under a main action.
 *
 * O1 and O2 end their bar with one: "New to ShikkhokPlus? **Create
 * account**", "Already have an account? **Log in**". The link is a 48dp
 * target although it reads as inline text, so it is no harder to hit
 * than a button.
 *
 * @param prompt The grey question
 * @param link The bold link's text
 * @param onClick Called when the link is tapped
 * @param modifier The layout modifier, for the whole line
 * @param linkModifier Applied to the link, for a test tag
 */
@Composable
fun PromptLink(
    prompt: String,
    link: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    linkModifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            prompt,
            style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Normal),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        TextButton(
            onClick = onClick,
            contentPadding = PaddingValues(horizontal = 4.dp),
            modifier = linkModifier.heightIn(min = Reach.touch),
        ) {
            Text(
                link,
                style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold),
                color = MaterialTheme.colorScheme.primary,
            )
        }
    }
}
