package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

/**
 * The shared surfaces every screen is built from.
 *
 * **Tone, not shadow.** A card is a lighter surface on a tinted page,
 * with no elevation at all. That is the design's depth rule and it has
 * two reasons: a 2dp shadow is invisible in sunlight, and drawing it
 * costs frames on the phones this product targets.
 */

/**
 * One card in a list.
 *
 * 12dp radius and 16dp padding, per the shape and spacing scales.
 *
 * @param modifier The layout modifier
 * @param onClick Called when tapped, or null for a card that is not
 *   interactive — a null here means no ripple and no accessibility
 *   focus, which is correct for a read-only card and wrong for a
 *   tappable one
 * @param content The card's contents
 */
@Composable
fun ShikkhokCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(
                MaterialTheme.colorScheme.surface,
                MaterialTheme.shapes.medium,
            )
            .then(
                if (onClick != null) {
                    // heightIn, not height: a fixed height would clip
                    // a Bangla conjunct at a large font scale, which
                    // is the failure the type scale exists to avoid.
                    Modifier
                        .heightIn(min = Reach.rowTwoLine)
                        .clickable(onClick = onClick)
                } else {
                    Modifier
                }
            )
            .padding(horizontal = Spacing.screen, vertical = Spacing.listItem),
        verticalArrangement = Arrangement.spacedBy(6.dp),
        content = content,
    )
}

/**
 * What a screen shows when there is nothing to show.
 *
 * **No illustration.** The design is explicit: it costs data and says
 * nothing. The title states the fact, the body explains what the thing
 * is and what to do, and the action follows.
 *
 * @param title The fact, in a few words
 * @param body What this is and what to do about it
 * @param modifier The layout modifier
 * @param action The primary action, or nothing
 */
@Composable
fun EmptyState(
    title: String,
    body: String,
    modifier: Modifier = Modifier,
    action: @Composable (() -> Unit)? = null,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(Spacing.section),
        verticalArrangement = Arrangement.spacedBy(Spacing.tight, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurface,
            textAlign = TextAlign.Center,
        )
        Text(
            text = body,
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        if (action != null) {
            Column(Modifier.padding(top = Spacing.tight)) { action() }
        }
    }
}

/**
 * A loading placeholder: one static grey block.
 *
 * **Static, deliberately.** The design forbids shimmer: animating a
 * skeleton costs frames on a low-end phone, which is the device most
 * likely to be waiting in the first place. The block is sized to the
 * real content's row so the list does not jump when it arrives.
 *
 * @param widthFraction How much of the line this block fills
 * @param height The block's height
 * @param modifier The layout modifier
 */
@Composable
fun SkeletonBlock(
    widthFraction: Float,
    height: androidx.compose.ui.unit.Dp,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier
            .fillMaxWidth(widthFraction)
            .heightIn(min = height)
            .background(
                MaterialTheme.colorScheme.surfaceContainerHigh,
                RoundedCornerShape(4.dp),
            ),
    ) {
        // Intentionally empty: a skeleton draws nothing but its block.
        Column(Modifier.heightIn(min = height)) {}
    }
}
