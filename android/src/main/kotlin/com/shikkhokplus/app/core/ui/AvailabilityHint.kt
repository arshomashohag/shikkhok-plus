package com.shikkhokplus.app.core.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import com.shikkhokplus.app.R
import com.shikkhokplus.app.feature.auth.MessageKeys

/** The availability line under a username field. */
const val TAG_AVAILABILITY_HINT: String = "username_availability_hint"

/**
 * The line under a username field: the help, "Checking…", "Available",
 * the server's refusal, or "could not check" (functional-spec 3.1).
 *
 * **Text, never colour alone**, and a polite live region so TalkBack
 * reads the answer when it arrives (functional-spec § 7). It renders the
 * state and decides nothing.
 *
 * @param state What the checker said
 * @param help The guidance shown while there is nothing to report, or null
 * @param modifier The layout modifier
 */
@Composable
fun AvailabilityHint(
    state: AvailabilityState,
    help: String?,
    modifier: Modifier = Modifier,
) {
    val colors = MaterialTheme.colorScheme
    val (text, color) =
        when (state) {
            AvailabilityState.Idle -> (help ?: return) to colors.onSurfaceVariant
            AvailabilityState.Checking -> stringResource(R.string.username_checking) to colors.onSurfaceVariant
            AvailabilityState.Available -> stringResource(R.string.username_available) to colors.primary
            is AvailabilityState.Refused -> stringResource(MessageKeys.resolve(state.messageKey)) to colors.error
            AvailabilityState.CouldNotCheck ->
                stringResource(R.string.username_could_not_check) to colors.onSurfaceVariant
        }
    Text(
        text = text,
        color = color,
        style = MaterialTheme.typography.bodySmall,
        modifier =
            modifier
                .semantics { liveRegion = LiveRegionMode.Polite }
                .testTag(TAG_AVAILABILITY_HINT),
    )
}
