package com.shikkhokplus.app.core.designsystem

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathData
import androidx.compose.ui.graphics.vector.rememberVectorPainter
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R

/**
 * The frame every screen sits in.
 *
 * **The missing piece, and the reason the app read as unstyled.** The
 * colour, type, spacing and reach scales were all specified and all
 * good — 7:1 contrast chosen for direct sun on a budget LCD, a touch
 * floor of 48dp, a spacing step per stated job. No screen used a
 * `Scaffold`, so none had an app bar, a title, a consistent margin or
 * anywhere for a snackbar to appear. A page of stacked default
 * controls reads as old whatever its palette is.
 *
 * **One title, one margin, one max width.** The width bound matters
 * more than it looks: a form at full width on a tablet or a large
 * phone gives lines nobody wants to read and buttons stretched to the
 * edges. 480dp holds a form at a comfortable measure and does nothing
 * at all on a small phone, where the screen is narrower anyway.
 *
 * @param title What this screen is, shown in the bar
 * @param modifier The layout modifier
 * @param scrollable Whether the content scrolls. A form must, because
 *   the keyboard takes half the screen; a list must not, because the
 *   list scrolls itself and nesting two scrollers breaks both
 * @param bottomBar The navigation bar, on a screen that is a tab
 *   destination. Empty by default: a screen pushed onto the stack
 *   shows no tabs, because tapping one from there would leave a
 *   half-finished task behind the bar.
 * @param content The screen's own contents, in a column
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScreenScaffold(
    title: String,
    modifier: Modifier = Modifier,
    scrollable: Boolean = true,
    onBack: (() -> Unit)? = null,
    bottomBar: @Composable () -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        modifier = modifier.fillMaxSize(),
        // A tab destination can be a form-shaped screen: the overview
        // scrolls as one column and is still a tab.
        bottomBar = bottomBar,
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleLarge,
                    )
                },
                // **A back arrow when the screen was pushed.** A form
                // reached from a list needs a way out that is not the
                // system gesture alone: a device with three-button
                // navigation has one, but the affordance should be on
                // screen either way.
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(
                            onClick = onBack,
                            modifier = Modifier.testTag(TAG_SCAFFOLD_BACK),
                        ) {
                            // **An inline vector, not a Material icon.**
                            // `material-icons-extended` is not a
                            // dependency here, and adding it would mean
                            // regenerating the Gradle lockfile and 581
                            // checksums for one arrow.
                            BackArrow(
                                contentDescription =
                                    stringResource(R.string.action_back),
                            )
                        }
                    }
                },
                colors =
                    TopAppBarDefaults.topAppBarColors(
                        // The page tone, not a raised surface: this
                        // design carries depth as tone and has no
                        // elevations outside bottom sheets.
                        containerColor = MaterialTheme.colorScheme.background,
                        titleContentColor = MaterialTheme.colorScheme.onSurface,
                        navigationIconContentColor =
                            MaterialTheme.colorScheme.onSurface,
                    ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { inner ->
        ScreenBody(
            inner = inner,
            scrollable = scrollable,
            content = content,
        )
    }
}

/**
 * The frame for a screen whose content is a list.
 *
 * **Separate from [ScreenScaffold] because a `LazyColumn` must own its
 * own scrolling.** Putting one inside a `verticalScroll` column gives
 * it unbounded height: it renders every row at once, which defeats the
 * laziness entirely and throws on some Compose versions rather than
 * merely performing badly. Eleven of this app's screens are lists, so
 * the distinction is worth a second entry point rather than a boolean
 * that is easy to get wrong.
 *
 * The caller supplies the `LazyColumn` itself, because only it knows
 * its keys, its content type and its item layout.
 *
 * @param title What this screen is, shown in the bar
 * @param modifier The layout modifier
 * @param subtitle A count or status under the title, inside the bar,
 *   as the design's `.ab` block draws it
 * @param header Anything fixed above the list — a staleness notice,
 *   say — which does not scroll with it
 * @param bottomBar The navigation bar, on a screen that is a tab
 *   destination. Empty by default: a screen pushed onto the stack
 *   shows no tabs, because tapping one from there would leave a
 *   half-finished task behind the bar.
 * @param content The list, and anything else that scrolls with it
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ListScreenScaffold(
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    header: @Composable ColumnScope.() -> Unit = {},
    bottomBar: @Composable () -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        modifier = modifier.fillMaxSize(),
        // **The bottom bar belongs to the Scaffold, not the content.**
        // Placed inside the column it would scroll away with the list,
        // and the list's own bottom inset would be wrong.
        bottomBar = bottomBar,
        topBar = {
            TopAppBar(
                title = {
                    // **The count sits INSIDE the bar, under the
                    // title.** The design draws `.ab` as one 64dp
                    // block holding `.h1` and `.sub` together; as a
                    // separate band below the bar it read as a second
                    // header rather than part of the first.
                    Column {
                        Text(
                            text = title,
                            style = MaterialTheme.typography.titleLarge,
                        )
                        if (subtitle != null) {
                            Text(
                                text = subtitle,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                },
                colors =
                    TopAppBarDefaults.topAppBarColors(
                        containerColor = MaterialTheme.colorScheme.background,
                        titleContentColor = MaterialTheme.colorScheme.onSurface,
                    ),
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
    ) { inner ->
        Column(
            modifier =
                Modifier
                    .fillMaxSize()
                    .padding(inner),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Column(
                modifier =
                    Modifier
                        .fillMaxSize()
                        .widthIn(max = 480.dp)
                        .padding(horizontal = Spacing.screen),
                verticalArrangement = Arrangement.spacedBy(Spacing.tight),
            ) {
                header()
                content()
            }
        }
    }
}

/**
 * The content column, shared by both scaffold shapes.
 *
 * @param inner The scaffold's own insets
 * @param scrollable Whether to wrap in a scroller
 * @param content The screen's contents
 */
@Composable
private fun ScreenBody(
    inner: PaddingValues,
    scrollable: Boolean,
    content: @Composable ColumnScope.() -> Unit,
) {
    val outer =
        Modifier
            .fillMaxSize()
            .padding(inner)
    val inner2 =
        Modifier
            .fillMaxWidth()
            // Holds a form at a readable measure on a tablet and does
            // nothing on a phone.
            .widthIn(max = 480.dp)
            .padding(horizontal = Spacing.screen)

    Column(
        modifier = outer,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Column(
            modifier =
                if (scrollable) {
                    inner2.verticalScroll(rememberScrollState())
                } else {
                    inner2
                },
            verticalArrangement = Arrangement.spacedBy(Spacing.screen),
            content = content,
        )
    }
}

/** The scaffold's back arrow. Not user-visible text. */
const val TAG_SCAFFOLD_BACK: String = "scaffold_back"

/**
 * A back arrow, drawn rather than imported.
 *
 * `autoMirrored` so it points the other way in a right-to-left locale.
 *
 * @param contentDescription What TalkBack announces
 */
@Composable
private fun BackArrow(contentDescription: String) {
    Icon(
        painter =
            rememberVectorPainter(
                ImageVector.Builder(
                    defaultWidth = 24.dp,
                    defaultHeight = 24.dp,
                    viewportWidth = 24f,
                    viewportHeight = 24f,
                    autoMirror = true,
                ).apply {
                    addPath(
                        pathData =
                            PathData {
                                moveTo(20f, 11f)
                                horizontalLineTo(7.83f)
                                lineTo(13.42f, 5.41f)
                                lineTo(12f, 4f)
                                lineTo(4f, 12f)
                                lineTo(12f, 20f)
                                lineTo(13.41f, 18.59f)
                                lineTo(7.83f, 13f)
                                horizontalLineTo(20f)
                                close()
                            },
                        fill = SolidColor(Color.Black),
                    )
                }.build(),
            ),
        contentDescription = contentDescription,
        tint = MaterialTheme.colorScheme.onSurface,
    )
}
