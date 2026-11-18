package com.shikkhokplus.app.feature.hublisting.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.TonalButton
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hublisting.FeedbackAnswer
import com.shikkhokplus.app.feature.hublisting.HubFeedbackState

/**
 * Tag for one reply's button.
 *
 * @param answer The reply
 * @return The tag
 */
fun hubFeedbackTag(answer: FeedbackAnswer): String = "hub_feedback_${answer.wire}"

/**
 * What the demand question's screen can do.
 *
 * @property onAnswer Sends a reply
 * @property onRetry Sends the reply that last failed again
 * @property onBack Leaves the screen
 */
data class HubFeedbackActions(
    val onAnswer: (FeedbackAnswer) -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * "Did the hub bring you a student?", with its three replies. The reply
 * the server accepted is drawn filled; a failed send leaves it as it was
 * and offers Retry [TC-8].
 *
 * @param state What to render
 * @param actions What the buttons do
 * @param modifier Layout modifier from the caller
 */
@Composable
fun HubFeedbackScreen(
    state: HubFeedbackState,
    actions: HubFeedbackActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.hub_feedback_title),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        Text(stringResource(R.string.hub_feedback_question), style = MaterialTheme.typography.titleLarge)
        Text(
            stringResource(R.string.hub_feedback_day, Numerals.count(state.day)),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        FeedbackAnswer.entries.forEach { answer ->
            val label = stringResource(labelOf(answer))
            val tagged = Modifier.fillMaxWidth().testTag(hubFeedbackTag(answer))
            val enabled = state.sending == null
            if (state.saved == answer) {
                TonalButton(label, { actions.onAnswer(answer) }, tagged, enabled)
            } else {
                SecondaryButton(label, { actions.onAnswer(answer) }, tagged, enabled)
            }
        }
        if (state.saved != null && state.failure == null) {
            Banner(title = stringResource(R.string.hub_feedback_thanks))
        }
        state.failure?.let { failure ->
            Banner(
                title = stringResource(R.string.hub_feedback_failed),
                body = stringResource(MessageKeys.resolve(failure.messageKey)),
                tone = BannerTone.ERROR,
                action =
                    if (failure.canRetry) {
                        { TextAction(stringResource(R.string.auth_retry), actions.onRetry) }
                    } else {
                        null
                    },
            )
        }
    }
}

/**
 * The string for a reply.
 *
 * @param answer The reply
 * @return Its string resource
 */
private fun labelOf(answer: FeedbackAnswer): Int =
    when (answer) {
        FeedbackAnswer.YES -> R.string.hub_feedback_yes
        FeedbackAnswer.NOT_YET -> R.string.hub_feedback_not_yet
        FeedbackAnswer.NOT_SURE -> R.string.hub_feedback_not_sure
    }
