package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.graphics.Color
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.border
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
    // A white card, title 18/30 SemiBold and body 14/22 Regular
    // (Components.dc.html, "Empty"). The body was labelLarge, which is
    // SemiBold, so explanatory text read as a heading.
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .padding(horizontal = Spacing.screen, vertical = Spacing.section),
        verticalArrangement = Arrangement.spacedBy(Spacing.tight),
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
            color = MaterialTheme.colorScheme.onSurface,
        )
        Text(
            text = body,
            style = BodyCompact,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (action != null) {
            Column(Modifier.padding(top = Spacing.tight)) { action() }
        }
    }
}

/**
 * A read that failed: a white card with an error outline, what went
 * wrong, and an outlined "Try again" when the server says a retry can
 * help (Components.dc.html, "Error").
 *
 * @param title What failed, as a short heading
 * @param body What it means or what to do
 * @param modifier The layout modifier
 * @param retryLabel The retry button's text
 * @param onRetry Called to retry, or null when a retry cannot help
 */
@Composable
fun ErrorCard(
    title: String,
    body: String?,
    modifier: Modifier = Modifier,
    retryLabel: String? = null,
    onRetry: (() -> Unit)? = null,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .border(1.5.dp, MaterialTheme.colorScheme.error, MaterialTheme.shapes.medium)
            .padding(horizontal = Spacing.screen, vertical = Spacing.listItem),
        verticalArrangement = Arrangement.spacedBy(Spacing.tight),
    ) {
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )
        body?.let {
            Text(text = it, style = BodyCompact, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (onRetry != null && retryLabel != null) {
            SecondaryButton(text = retryLabel, onClick = onRetry, modifier = Modifier.testTag(TAG_ERROR_RETRY))
        }
    }
}

/** How strongly a banner speaks. */
enum class BannerTone {
    /** Something to know: a pale blue panel. */
    INFO,

    /** A refusal to act on: a pale red panel. */
    ERROR,

    /** A neutral fact, such as being offline: a grey panel. */
    NEUTRAL,
}

/**
 * A banner inside the page: a bold first line and an optional second.
 *
 * @param title The first line, bold
 * @param modifier The layout modifier
 * @param body A second line, or null
 * @param tone Which panel colour
 * @param action Drawn at the end, such as a link
 */
@Composable
fun Banner(
    title: String,
    modifier: Modifier = Modifier,
    body: String? = null,
    tone: BannerTone = BannerTone.INFO,
    action: @Composable (() -> Unit)? = null,
) {
    val colors = MaterialTheme.colorScheme
    val (container, content) =
        when (tone) {
            BannerTone.INFO -> colors.tertiaryContainer to colors.onTertiaryContainer
            BannerTone.ERROR -> colors.errorContainer to colors.onErrorContainer
            BannerTone.NEUTRAL -> colors.surfaceContainerHigh to colors.onSurface
        }
    Column(
        modifier = modifier
            .fillMaxWidth()
            .background(container, MaterialTheme.shapes.medium)
            .then(
                if (tone == BannerTone.INFO) {
                    Modifier.border(1.5.dp, colors.primary, MaterialTheme.shapes.medium)
                } else {
                    Modifier
                },
            )
            .padding(horizontal = 14.dp, vertical = Spacing.listItem),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(text = title, style = BodyCompact.copy(fontWeight = FontWeight.Bold), color = content)
        body?.let { Text(text = it, style = BodyCompact, color = content) }
        action?.invoke()
    }
}

/**
 * A placeholder list row: a 40dp circle and two lines, sized to a real
 * 72dp row so nothing jumps when the content arrives.
 *
 * @param modifier The layout modifier
 */
@Composable
fun SkeletonRow(modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = Reach.rowTwoLine)
            .padding(horizontal = Spacing.screen),
        horizontalArrangement = Arrangement.spacedBy(Spacing.listItem),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(40.dp)
                .background(MaterialTheme.colorScheme.surfaceContainerHigh, CircleShape),
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            SkeletonBlock(widthFraction = 0.6f, height = 16.dp)
            SkeletonBlock(
                widthFraction = 0.4f,
                height = 12.dp,
                colour = MaterialTheme.colorScheme.surfaceContainer,
            )
        }
    }
}

/**
 * A list still loading: several placeholder rows on a white card.
 *
 * @param rows How many rows to draw
 * @param modifier The layout modifier
 */
@Composable
fun SkeletonList(rows: Int = 4, modifier: Modifier = Modifier) {
    Column(
        modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
            .testTag(TAG_SKELETON),
    ) {
        repeat(rows) { SkeletonRow() }
    }
}

/** The retry button inside an [ErrorCard]. */
const val TAG_ERROR_RETRY: String = "error_retry"

/** A list's loading placeholder. */
const val TAG_SKELETON: String = "skeleton"

/** Explanatory text at 14/22 Regular, the design's `.t14`. */
val BodyCompact: TextStyle
    @Composable get() = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Normal)

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
 * @param colour The block's tone; second lines are a step lighter
 */
@Composable
fun SkeletonBlock(
    widthFraction: Float,
    height: androidx.compose.ui.unit.Dp,
    modifier: Modifier = Modifier,
    colour: Color = MaterialTheme.colorScheme.surfaceContainerHigh,
) {
    Column(
        modifier
            .fillMaxWidth(widthFraction)
            .heightIn(min = height)
            .background(colour, RoundedCornerShape(4.dp)),
    ) {
        // Intentionally empty: a skeleton draws nothing but its block.
        Column(Modifier.heightIn(min = height)) {}
    }
}
