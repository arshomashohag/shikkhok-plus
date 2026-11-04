package com.shikkhokplus.app.feature.profile.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.BodyCompact
import com.shikkhokplus.app.core.designsystem.DestructiveButton
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.core.designsystem.statusColors
import com.shikkhokplus.app.core.format.Numerals

/** The control that logs out. */
const val TAG_LOG_OUT_CONFIRM: String = "log_out_confirm"

/** The control that stays signed in. */
const val TAG_LOG_OUT_STAY: String = "log_out_stay"

/**
 * Confirm logging out, and say what it would discard (T9 "Log out ·
 * unsent work warning").
 *
 * **Never silent about unsent work.** Logging out discards this
 * account's unsent writes from the phone, so a class record saved and
 * not yet sent is lost. With work waiting, the sheet leads with the
 * count in the amber callout and makes *staying* the filled, first
 * choice; logging out is the red outlined one under it. With nothing
 * waiting there is nothing to warn about, and the sheet is a plain
 * confirmation.
 *
 * The count and the discard are both scoped to this account by the
 * queue store; another account's writes on the same phone are neither
 * counted nor touched.
 *
 * @param unsent How many saved writes have not been sent
 * @param onConfirm Called to log out
 * @param onDismiss Called to stay signed in
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LogOutSheet(unsent: Int, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier =
                Modifier
                    .fillMaxWidth()
                    .padding(start = Spacing.screen, end = Spacing.screen, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(Spacing.listItem),
        ) {
            Text(
                text = stringResource(R.string.log_out_title),
                style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold),
                modifier = Modifier.asHeading(),
            )
            if (unsent > 0) {
                UnsentCallout(unsent)
                PrimaryButton(
                    text = stringResource(R.string.log_out_stay),
                    onClick = onDismiss,
                    modifier = Modifier.fillMaxWidth().testTag(TAG_LOG_OUT_STAY),
                )
                DestructiveButton(
                    text = stringResource(R.string.log_out_anyway),
                    onClick = onConfirm,
                    modifier = Modifier.fillMaxWidth().testTag(TAG_LOG_OUT_CONFIRM),
                )
            } else {
                Text(
                    text = stringResource(R.string.sign_out_body),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                PrimaryButton(
                    text = stringResource(R.string.log_out_confirm),
                    onClick = onConfirm,
                    modifier = Modifier.fillMaxWidth().testTag(TAG_LOG_OUT_CONFIRM),
                )
                SecondaryButton(
                    text = stringResource(R.string.action_cancel),
                    onClick = onDismiss,
                    modifier = Modifier.fillMaxWidth().testTag(TAG_LOG_OUT_STAY),
                )
            }
        }
    }
}

/**
 * The amber callout: how many records would be lost, and that logging
 * out deletes them from this phone.
 *
 * @param unsent How many saved writes have not been sent
 */
@Composable
private fun UnsentCallout(unsent: Int) {
    val status = MaterialTheme.statusColors
    Column(
        modifier =
            Modifier
                .fillMaxWidth()
                .background(status.partialContainer, MaterialTheme.shapes.medium)
                .padding(horizontal = 14.dp, vertical = Spacing.listItem),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Text(
            text = stringResource(R.string.log_out_unsent_title, Numerals.count(unsent)),
            style = BodyCompact.copy(fontWeight = FontWeight.Bold),
            color = status.onPartialContainer,
        )
        Text(
            text = stringResource(R.string.log_out_unsent_body),
            style = BodyCompact,
            color = status.onPartialContainer,
        )
    }
}
