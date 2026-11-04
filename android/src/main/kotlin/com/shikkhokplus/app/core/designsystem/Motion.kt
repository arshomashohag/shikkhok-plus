package com.shikkhokplus.app.core.designsystem

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp

/**
 * The app's motion: few moves, each carrying information.
 *
 * **Two durations, and both short.** Content arriving fades in over
 * [ENTER_MS]; content leaving fades out over [EXIT_MS], faster, so the
 * old screen is gone before the new one is readable rather than the
 * two overlapping. Nothing slides across the screen or bounces: on a
 * budget phone a long animation is time spent waiting, and a teacher
 * mid-class has none to spend.
 *
 * Compose scales every duration here by the system's animator duration
 * scale, so "Remove animations" in the accessibility settings turns
 * them off without anything in this file knowing about it.
 */
object Motion {
    /** Content arriving. */
    const val ENTER_MS: Int = 220

    /** Content leaving. */
    const val EXIT_MS: Int = 90
}

/**
 * Fade between a screen's states — loading, loaded, empty, failed.
 *
 * **Keyed on the kind of state, not its contents.** Going from the
 * skeleton to the list fades; a list replaced by a newer list of the
 * same kind (a pull-to-refresh answer, a filter) does not, because
 * re-fading content the person is reading would be noise, not news.
 *
 * Size changes are not animated: a list's height jumping into place is
 * cheaper and steadier than one animating its own size while it also
 * lays out lazily.
 *
 * @param state The screen's current state
 * @param spacing The gap between the state's children, matching the
 *   scaffold the screen sits in
 * @param modifier The layout modifier
 * @param content Renders one state, in a column
 */
@Composable
fun <S : Any> StateFade(
    state: S,
    spacing: Dp,
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.(S) -> Unit,
) {
    AnimatedContent(
        targetState = state,
        modifier = modifier,
        contentKey = { it::class },
        transitionSpec = {
            (fadeIn(tween(Motion.ENTER_MS)) togetherWith fadeOut(tween(Motion.EXIT_MS))).using(null)
        },
        label = "state",
    ) { shown ->
        Column(verticalArrangement = Arrangement.spacedBy(spacing)) { content(shown) }
    }
}
