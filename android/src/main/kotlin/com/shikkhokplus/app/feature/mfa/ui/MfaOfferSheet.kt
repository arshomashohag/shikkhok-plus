package com.shikkhokplus.app.feature.mfa.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.asHeading

/** Turn on, on the offer. */
const val TAG_MFA_OFFER_TURN_ON: String = "mfa_offer_turn_on"

/** Not now, on the offer. */
const val TAG_MFA_OFFER_LATER: String = "mfa_offer_later"

/**
 * The one-time offer to turn on two-step verification, made after
 * signing in to an account the server recommends it for [0028].
 *
 * **Dismissing it is an answer.** Swiping the sheet away counts as Not
 * now, so the offer is not made again on this phone; More keeps a
 * "Recommended" mark on its row until it is on.
 *
 * @param onTurnOn Called to go and turn it on
 * @param onNotNow Called to put it off, by the button or by dismissing
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MfaOfferSheet(onTurnOn: () -> Unit, onNotNow: () -> Unit) {
    ModalBottomSheet(
        onDismissRequest = onNotNow,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
    ) {
        MfaOfferContent(onTurnOn, onNotNow)
    }
}

/**
 * What the offer holds, apart from the sheet, so a test can render it
 * without a modal window.
 *
 * @param onTurnOn Called to go and turn it on
 * @param onNotNow Called to put it off
 */
@Composable
internal fun MfaOfferContent(onTurnOn: () -> Unit, onNotNow: () -> Unit) {
    Column(
        modifier =
            Modifier
                .fillMaxWidth()
                .padding(start = Spacing.screen, end = Spacing.screen, bottom = 18.dp),
        verticalArrangement = Arrangement.spacedBy(Spacing.listItem),
    ) {
        Text(
            text = stringResource(R.string.two_step_offer_title),
            style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
            modifier = Modifier.asHeading(),
        )
        Text(
            text = stringResource(R.string.two_step_offer_body),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        PrimaryButton(
            text = stringResource(R.string.two_step_turn_on),
            onClick = onTurnOn,
            modifier = Modifier.fillMaxWidth().testTag(TAG_MFA_OFFER_TURN_ON),
        )
        SecondaryButton(
            text = stringResource(R.string.two_step_offer_later),
            onClick = onNotNow,
            modifier = Modifier.fillMaxWidth().testTag(TAG_MFA_OFFER_LATER),
        )
    }
}
