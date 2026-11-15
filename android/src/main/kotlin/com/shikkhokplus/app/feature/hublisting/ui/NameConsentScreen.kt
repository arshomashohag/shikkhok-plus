package com.shikkhokplus.app.feature.hublisting.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hublisting.ConsentRow
import com.shikkhokplus.app.feature.hublisting.NameConsentBody
import com.shikkhokplus.app.feature.hublisting.NameConsentState

/**
 * Tag for one centre's consent checkbox.
 *
 * @param centreId The centre
 * @return The tag
 */
fun nameConsentTag(centreId: String): String = "name_consent_$centreId"

/**
 * "Show my name on the centre's public listing": one checkbox per
 * accepted centre membership. The box shows the server's last answer; a
 * failed write leaves it as it was and offers Retry [TC-8].
 *
 * @param state What to render
 * @param onSet Called with the centre and the wanted choice
 * @param onRetry Called with the centre whose write to repeat
 * @param onRetryLoad Reads the list again
 * @param onBack Leaves the screen
 * @param modifier Layout modifier from the caller
 */
@Composable
fun NameConsentScreen(
    state: NameConsentState,
    onSet: (String, Boolean) -> Unit,
    onRetry: (String) -> Unit,
    onRetryLoad: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.hub_consent_title), modifier = modifier, onBack = onBack) {
        when (val body = state.body) {
            NameConsentBody.Loading -> SkeletonList(rows = 2)
            is NameConsentBody.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = null,
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) onRetryLoad else null,
                )
            is NameConsentBody.Loaded -> {
                if (body.rows.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.hub_consent_title),
                        body = stringResource(R.string.hub_consent_empty),
                    )
                }
                body.rows.forEach { ConsentCard(it, onSet, onRetry) }
                Text(
                    stringResource(R.string.hub_consent_help),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun ConsentCard(row: ConsentRow, onSet: (String, Boolean) -> Unit, onRetry: (String) -> Unit) {
    val centreId = row.membership.centreId
    ShikkhokCard {
        Text(row.membership.centreName, style = MaterialTheme.typography.titleMedium)
        Row(
            Modifier.fillMaxWidth().heightIn(min = Reach.touch),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Spacing.tight),
        ) {
            Checkbox(
                checked = row.membership.publicNameConsent,
                onCheckedChange = { onSet(centreId, it) },
                enabled = !row.busy,
                modifier = Modifier.testTag(nameConsentTag(centreId)),
            )
            Text(stringResource(R.string.hub_consent_toggle), style = MaterialTheme.typography.bodyLarge)
        }
        row.failureKey?.let { key ->
            Banner(
                title = stringResource(R.string.hub_consent_failed) + " " + stringResource(MessageKeys.resolve(key)),
                tone = BannerTone.ERROR,
                action = { TextAction(stringResource(R.string.auth_retry), { onRetry(centreId) }) },
            )
        }
    }
}
