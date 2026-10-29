package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** The bottom navigation bar. Not user-visible text. */
const val TAG_BOTTOM_NAV: String = "bottom_nav"

/**
 * One destination in the bottom bar.
 *
 * @property label What the tab is called
 * @property icon The 20dp line icon above the label
 * @property tag A stable test identifier
 * @property enabled Whether this destination can be opened. A tab
 *   whose screen has no network layer yet is shown DISABLED rather
 *   than hidden: hiding it would make the bar change shape as units
 *   land, and opening it would show a screen that cannot load.
 */
data class NavDestination(
    val label: String,
    val icon: Painter,
    val tag: String,
    val enabled: Boolean = true,
)

/**
 * The bottom navigation bar, as the design specifies it.
 *
 * **Missing entirely until now**, which is why the app had no way to
 * move between the teacher's own screens: every destination was
 * reachable only by pushing onto a stack and coming back.
 *
 * The design fixes its own measurements and they are followed rather
 * than taken from M3's `NavigationBar`, whose 80dp height, active
 * indicator and ripple do not match:
 *
 * - a white bar on the tinted page, with a 1dp top divider;
 * - a 56×30dp pill behind the selected icon only, radius 15dp,
 *   `primaryContainer` on `onPrimaryContainer`;
 * - a 13sp label, `onSurfaceVariant` unselected, `onSurface` and bold
 *   when selected — weight carries the state as well as colour, so it
 *   survives a colour-blind reading and direct sun.
 *
 * Each tab is `selectable` with `Role.Tab`, so TalkBack announces it as
 * a tab and states its selection; a `Row` of clickable columns would be
 * announced as four unrelated buttons.
 *
 * @param destinations The tabs, in order
 * @param selectedIndex Which tab is current
 * @param onSelect Called with the index the person chose
 * @param modifier The layout modifier
 */
@Composable
fun BottomNav(
    destinations: List<NavDestination>,
    selectedIndex: Int,
    onSelect: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth().testTag(TAG_BOTTOM_NAV),
        color = MaterialTheme.colorScheme.surface,
    ) {
        Column {
            // The boards draw this line at #E4E8EE, lighter than a list divider.
            HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
            Row(
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp, bottom = 12.dp),
                horizontalArrangement = Arrangement.SpaceEvenly,
            ) {
                destinations.forEachIndexed { index, destination ->
                    NavItem(
                        destination = destination,
                        selected = index == selectedIndex,
                        onClick = { onSelect(index) },
                        modifier = Modifier.weight(1f),
                    )
                }
            }
        }
    }
}

/**
 * One tab.
 *
 * @param destination What this tab is
 * @param selected Whether it is the current one
 * @param onClick Called when chosen
 * @param modifier The layout modifier
 */
@Composable
private fun NavItem(
    destination: NavDestination,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier =
            modifier
                // The whole column is the target, not the icon: the
                // pill is 30dp tall and would be under the 48dp floor
                // on its own.
                .heightIn(min = Reach.touch)
                .selectable(
                    selected = selected,
                    enabled = destination.enabled,
                    role = Role.Tab,
                    onClick = onClick,
                )
                .testTag(destination.tag),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Column(
            modifier =
                Modifier
                    .width(56.dp)
                    .height(30.dp)
                    .background(
                        color =
                            if (selected) {
                                MaterialTheme.colorScheme.primaryContainer
                            } else {
                                MaterialTheme.colorScheme.surface
                            },
                        shape = RoundedCornerShape(15.dp),
                    ),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Icon(
                painter = destination.icon,
                // The label names the destination, so the icon is
                // decorative and must not be announced twice.
                contentDescription = null,
                modifier = Modifier.size(20.dp),
                tint =
                    when {
                        !destination.enabled -> MaterialTheme.colorScheme.outline
                        selected -> MaterialTheme.colorScheme.onPrimaryContainer
                        else -> MaterialTheme.colorScheme.onSurfaceVariant
                    },
            )
        }
        Text(
            text = destination.label,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
            color =
                when {
                    // `outline` is the design's 4.6:1 token and is for
                    // borders and icons, never body text -- which is
                    // exactly right for a label that must read as
                    // unavailable rather than merely quiet.
                    !destination.enabled -> MaterialTheme.colorScheme.outline
                    selected -> MaterialTheme.colorScheme.onSurface
                    else -> MaterialTheme.colorScheme.onSurfaceVariant
                },
        )
    }
}
