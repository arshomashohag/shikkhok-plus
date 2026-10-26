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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

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
 * @param content The screen's own contents, in a column
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScreenScaffold(
    title: String,
    modifier: Modifier = Modifier,
    scrollable: Boolean = true,
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        modifier = modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleLarge,
                    )
                },
                colors =
                    TopAppBarDefaults.topAppBarColors(
                        // The page tone, not a raised surface: this
                        // design carries depth as tone and has no
                        // elevations outside bottom sheets.
                        containerColor = MaterialTheme.colorScheme.background,
                        titleContentColor = MaterialTheme.colorScheme.onSurface,
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
 * @param header Anything fixed above the list — a summary line, a
 *   staleness notice — which does not scroll with it
 * @param content The list, and anything else that scrolls with it
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ListScreenScaffold(
    title: String,
    modifier: Modifier = Modifier,
    header: @Composable ColumnScope.() -> Unit = {},
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        modifier = modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleLarge,
                    )
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
