package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * The menu-list pieces the More screens are built from (T9, S4, G4).
 *
 * The artboards draw every More screen the same way: a profile card,
 * then white cards of rows under small upper-case section headers. Each
 * row is an outline icon, a title, an optional grey sub-label and a
 * chevron or a value at the end. These are those pieces, so the three
 * lenses' screens differ only in which rows they list.
 */

/**
 * The More screens' row icons, as outline vectors.
 *
 * **Inline vectors, not Material icons**, for the reason [RoleIcons]
 * gives: `material-icons-extended` is not a dependency, and adding it
 * would mean regenerating the Gradle lockfile and its checksums. The
 * path data is the artboards' own 24-unit SVG, with rectangles and
 * circles written out as paths.
 */
object MenuIcons {
    /** A phone: where students pay (T9). */
    val Phone: ImageVector =
        outline(
            "Phone",
            "M8.5 2.5h7a2.5 2.5 0 0 1 2.5 2.5v14a2.5 2.5 0 0 1-2.5 2.5h-7" +
                "a2.5 2.5 0 0 1-2.5-2.5v-14a2.5 2.5 0 0 1 2.5-2.5z",
            "M10.5 18.5h3",
        )

    /** An upward arrow from a line: records waiting to be sent (T9). */
    val Upload: ImageVector = outline("Upload", "M12 15V3M7 8l5-5 5 5M5 21h14")

    /** A downward arrow onto a line: records and reports (T9). */
    val Download: ImageVector = outline("Download", "M12 3v12M7 10l5 5 5-5M5 21h14")

    /** An envelope: invitations (S4, G4). */
    val Envelope: ImageVector =
        outline(
            "Envelope",
            "M5 5h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-14a2 2 0 0 1-2-2v-10a2 2 0 0 1 2-2z",
            "M3 7l9 6 9-6",
        )

    /** An adult beside a child: my children (G4). */
    val Children: ImageVector =
        outline(
            "Children",
            "M6 7a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
            "M14.8 10a2.2 2.2 0 1 0 4.4 0a2.2 2.2 0 1 0-4.4 0",
            "M3 20c0-4 3-6 6-6s6 2 6 6M14 20c0-2.5 1.5-4 3-4s3 1.5 3 4",
        )

    /** Three sliders: settings. */
    val Settings: ImageVector =
        outline("Settings", "M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1", "M15 4v4M9 10v4M17 16v4")

    /** Two arrows in a loop: switch role. */
    val Switch: ImageVector = outline("Switch", "M7 7h11l-3-3M17 17h-11l3 3")

    /** A door with an arrow leaving it: log out (T9, S4, G4). */
    val LogOut: ImageVector = outline("LogOut", "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10")

    /** A bin: delete account (T9). */
    val Delete: ImageVector = outline("Delete", "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3")

    /** A head and shoulders: the profile button (S4, G4). */
    val Person: ImageVector =
        outline("Person", "M8 8a4 4 0 1 0 8 0a4 4 0 1 0-8 0", "M4 21c0-4 4-6 8-6s8 2 8 6")

    /** An X: closes a pushed form (Edit profile). */
    val Close: ImageVector = outline("Close", "M6 6l12 12M18 6L6 18")

    /** The chevron at the end of a row that opens a screen. */
    val Chevron: ImageVector = outline("Chevron", "M9 6l6 6-6 6")

    /**
     * Build one 24-unit outline icon from SVG path data.
     *
     * @param name The vector's name
     * @param paths Each path's SVG `d` attribute
     * @return The icon
     */
    private fun outline(name: String, vararg paths: String): ImageVector =
        ImageVector
            .Builder(
                name = name,
                defaultWidth = 24.dp,
                defaultHeight = 24.dp,
                viewportWidth = 24f,
                viewportHeight = 24f,
            ).apply {
                paths.forEach { d ->
                    addPath(
                        pathData = addPathNodes(d),
                        stroke = SolidColor(Color.Black),
                        strokeLineWidth = STROKE,
                        strokeLineCap = StrokeCap.Round,
                        strokeLineJoin = StrokeJoin.Round,
                    )
                }
            }.build()

    /** The artboards' row-icon stroke width, in viewport units. */
    private const val STROKE = 2f
}

/** The profile button in a family home's bar. */
const val TAG_PROFILE_BUTTON: String = "profile_button"

/**
 * The profile button at a student's or guardian's home (S4, G4): their
 * way into More, which the artboards open from the bar rather than from
 * a bottom tab.
 *
 * @param label What a screen reader says; the More screen's name
 * @param onClick Called to open More
 */
@Composable
fun ProfileButton(label: String, onClick: () -> Unit) {
    androidx.compose.material3.IconButton(onClick = onClick, modifier = Modifier.testTag(TAG_PROFILE_BUTTON)) {
        Icon(imageVector = MenuIcons.Person, contentDescription = label, modifier = Modifier.size(24.dp))
    }
}

/**
 * A small upper-case section header ("GETTING PAID", "ACCOUNT").
 *
 * The design's `.sec`: 13/20 Bold in the secondary text colour, with a
 * little letter spacing, sitting just above its card.
 *
 * @param text The header, already upper-cased where the language has case
 * @param modifier The layout modifier
 */
@Composable
fun MenuSectionHeader(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        style =
            MaterialTheme.typography.labelSmall.copy(
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.5.sp,
            ),
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier =
            modifier
                .padding(start = 4.dp, top = Spacing.tight)
                .asHeading(),
    )
}

/**
 * One white card holding menu rows, with a hairline between rows.
 *
 * @param modifier The layout modifier
 * @param content The rows, each a [MenuRow]
 */
@Composable
fun MenuCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier =
            modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium),
        content = content,
    )
}

/** A hairline between two rows of one [MenuCard]. */
@Composable
fun MenuDivider() {
    HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
}

/**
 * What a row shows at its end.
 *
 * A row that opens a screen ends in a chevron. A row that acts in place
 * (log out, delete) ends in nothing, because a chevron would promise a
 * screen that is not there.
 */
sealed interface MenuTrailing {
    /** Opens another screen. */
    data object Chevron : MenuTrailing

    /** Acts in place, or is not tappable. */
    data object None : MenuTrailing

    /**
     * A count in a filled circle, such as pending invitations.
     *
     * @property text The count, already formatted
     */
    data class Badge(val text: String) : MenuTrailing
}

/**
 * One menu row: icon, title, optional sub-label, and a trailing mark.
 *
 * The design's `.mi`: at least 56dp tall (rows hold two lines of Bangla
 * at a large font scale, so `heightIn`, never a fixed height), a 22dp
 * icon, 16/26 SemiBold title over a 13/20 sub-label.
 *
 * @param title The row's title
 * @param onClick Called when tapped, or null for a row that only informs
 * @param modifier The layout modifier; tests tag the row through it
 * @param icon The leading icon, or null
 * @param subtitle The grey second line, or null
 * @param trailing What sits at the end
 * @param leading Drawn where the icon goes, for something richer than
 *   an icon such as a child's avatar; ignored when [icon] is set
 * @param highlighted Draws the row on the pale primary wash the design
 *   uses for something waiting on the person, such as an invitation
 * @param destructive Draws the title in the error colour (delete account)
 * @param enabled False greys the row and ignores taps, as offline does
 */
@Composable
fun MenuRow(
    title: String,
    onClick: (() -> Unit)?,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    subtitle: String? = null,
    trailing: MenuTrailing = MenuTrailing.Chevron,
    leading: @Composable (() -> Unit)? = null,
    highlighted: Boolean = false,
    destructive: Boolean = false,
    enabled: Boolean = true,
) {
    val colors = MaterialTheme.colorScheme
    val base = if (destructive) colors.error else colors.onSurface
    // A row that cannot act now (offline) keeps its place, greyed, so the
    // screen does not rearrange itself when the connection returns.
    val titleColor = if (enabled) base else base.copy(alpha = DISABLED_ALPHA)
    Row(
        modifier =
            modifier
                .fillMaxWidth()
                // The design's #EEF3FC is the primary container at half
                // strength over white; derived rather than hard-coded so
                // the dark theme gets its own wash.
                .then(
                    if (highlighted) {
                        Modifier.background(colors.primaryContainer.copy(alpha = HIGHLIGHT_ALPHA))
                    } else {
                        Modifier
                    },
                )
                .heightIn(min = LocalTouchScale.current.rowSingle)
                .then(
                    if (onClick != null) {
                        Modifier.clickable(role = Role.Button, enabled = enabled, onClick = onClick)
                    } else {
                        Modifier
                    },
                )
                .padding(start = Spacing.screen, end = Spacing.listItem, top = Spacing.tight, bottom = Spacing.tight),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = if (destructive) colors.error else colors.onSurfaceVariant,
                modifier = Modifier.size(22.dp),
            )
        } else {
            leading?.invoke()
        }
        Column(Modifier.weight(1f)) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium,
                color = titleColor,
            )
            subtitle?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.onSurfaceVariant,
                )
            }
        }
        when (trailing) {
            MenuTrailing.Chevron ->
                Icon(
                    imageVector = MenuIcons.Chevron,
                    contentDescription = null,
                    tint = colors.outline,
                    modifier = Modifier.size(20.dp),
                )
            is MenuTrailing.Badge -> CountBadge(trailing.text)
            MenuTrailing.None -> Unit
        }
    }
}

/**
 * A count in a filled primary circle, the design's `.badge`.
 *
 * @param text The count, already formatted
 */
@Composable
private fun CountBadge(text: String) {
    Box(
        modifier =
            Modifier
                .heightIn(min = 24.dp)
                .widthIn(min = 24.dp)
                .background(MaterialTheme.colorScheme.primary, CircleShape)
                .padding(horizontal = 7.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
            color = MaterialTheme.colorScheme.onPrimary,
            textAlign = TextAlign.Center,
        )
    }
}

/**
 * The profile card at the top of a More screen: avatar, name, a role
 * and number line, and an optional Edit pill.
 *
 * The design's `.prof`: a 52dp primary circle holding the name's first
 * letter, the name at 18/28 SemiBold, and the line under it at 13/20.
 *
 * @param initial The letter in the avatar
 * @param name The person's name, or a prompt to add one
 * @param line The second line, "Teacher · 01712-345678"
 * @param modifier The layout modifier
 * @param onEdit Called by the Edit pill, or null to draw none
 * @param editLabel The Edit pill's label
 * @param editTag The test tag on the Edit pill
 */
@Composable
fun ProfileCard(
    initial: String,
    name: String,
    line: String,
    modifier: Modifier = Modifier,
    onEdit: (() -> Unit)? = null,
    editLabel: String = "",
    editTag: String = "",
) {
    Row(
        modifier =
            modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
                .padding(horizontal = Spacing.screen, vertical = 14.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier =
                Modifier
                    .size(52.dp)
                    .background(MaterialTheme.colorScheme.primary, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = initial,
                style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
        Column(Modifier.weight(1f)) {
            Text(
                text = name,
                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold),
                color = MaterialTheme.colorScheme.onSurface,
            )
            Text(
                text = line,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        onEdit?.let {
            TonalButton(
                text = editLabel,
                onClick = it,
                modifier = Modifier.testTag(editTag),
            )
        }
    }
}

/** How faint a row that cannot act now is drawn. */
private const val DISABLED_ALPHA = 0.5f

/** How strongly a highlighted row's wash shows. */
private const val HIGHLIGHT_ALPHA = 0.5f
