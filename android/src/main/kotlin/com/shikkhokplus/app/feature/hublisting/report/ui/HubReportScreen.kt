package com.shikkhokplus.app.feature.hublisting.report.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.LocalTouchScale
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hublisting.report.HubReportState
import com.shikkhokplus.app.feature.hublisting.report.NOTE_MAX
import com.shikkhokplus.app.feature.hublisting.report.ReportKind
import com.shikkhokplus.app.feature.hublisting.report.ReportReason
import com.shikkhokplus.app.feature.hublisting.report.ReportTarget

/** Tag for the note field. */
const val TAG_HUB_REPORT_NOTE: String = "hub_report_note"

/**
 * Tag for one reason's row.
 *
 * @param reason The reason
 * @return The tag
 */
fun hubReportReasonTag(reason: ReportReason): String = "hub_report_reason_${reason.wire}"

/**
 * What the report screen can do.
 *
 * @property onReason Chooses a reason
 * @property onNote Changes the note
 * @property onSend Sends the report
 * @property onRetry Sends it again after a failure that can be retried
 * @property onBack Leaves the screen
 */
data class HubReportActions(
    val onReason: (ReportReason) -> Unit = {},
    val onNote: (String) -> Unit = {},
    val onSend: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * Report a public hub page: which page, a reason from the server's list
 * and an optional note. A link that named no valid page says so and
 * offers nothing to send; a sent report says what happens next.
 *
 * @param state What to render
 * @param actions What the controls do
 * @param modifier Layout modifier from the caller
 */
@Composable
fun HubReportScreen(
    state: HubReportState,
    actions: HubReportActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.hub_report_title),
        modifier = modifier,
        onBack = actions.onBack,
    ) {
        val target = state.target
        when {
            target == null ->
                Banner(
                    title = stringResource(R.string.hub_report_link_invalid),
                    body = stringResource(R.string.hub_report_link_invalid_body),
                    tone = BannerTone.ERROR,
                )
            state.sent -> Banner(title = stringResource(R.string.hub_report_sent))
            else -> ReportForm(target, state, actions)
        }
    }
}

/**
 * The form, for a valid target that has not been reported from here yet.
 *
 * @param target The page reported
 * @param state What to render
 * @param actions What the controls do
 */
@Composable
private fun ReportForm(
    target: ReportTarget,
    state: HubReportState,
    actions: HubReportActions,
) {
    Text(
        stringResource(kindLabel(target.kind)),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Text(stringResource(R.string.hub_report_reason_question), style = MaterialTheme.typography.titleMedium)
    Column(Modifier.fillMaxWidth().selectableGroup()) {
        ReportReason.entries.forEach { reason ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = LocalTouchScale.current.rowSingle)
                    .selectable(
                        selected = state.reason == reason,
                        enabled = !state.sending,
                        role = Role.RadioButton,
                        onClick = { actions.onReason(reason) },
                    ).padding(horizontal = 4.dp)
                    .testTag(hubReportReasonTag(reason)),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RadioButton(selected = state.reason == reason, onClick = null, enabled = !state.sending)
                Text(
                    stringResource(reasonLabel(reason)),
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(start = 12.dp).weight(1f),
                )
            }
        }
    }
    ShikkhokTextField(
        value = state.note,
        onValueChange = actions.onNote,
        label = stringResource(R.string.hub_report_note_label),
        help =
            stringResource(R.string.hub_report_note_help) + "  " +
                stringResource(
                    R.string.hub_report_note_count,
                    Numerals.count(state.note.length),
                    Numerals.count(NOTE_MAX),
                ),
        enabled = !state.sending,
        singleLine = false,
        minLines = 3,
        fieldModifier = Modifier.testTag(TAG_HUB_REPORT_NOTE),
    )
    state.failure?.let { failure ->
        Banner(
            title = stringResource(R.string.hub_report_failed),
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
    PrimaryButton(
        text = stringResource(if (state.sending) R.string.hub_report_sending else R.string.hub_report_send),
        onClick = actions.onSend,
        modifier = Modifier.fillMaxWidth(),
        enabled = state.canSend,
    )
}

/**
 * The words for the kind of page reported.
 *
 * @param kind The kind
 * @return Its string resource
 */
private fun kindLabel(kind: ReportKind): Int =
    when (kind) {
        ReportKind.OWNER_LISTING -> R.string.hub_report_target_owner
        ReportKind.BATCH_LISTING -> R.string.hub_report_target_batch
        ReportKind.MEDIA -> R.string.hub_report_target_media
    }

/**
 * The words for a reason.
 *
 * @param reason The reason
 * @return Its string resource
 */
private fun reasonLabel(reason: ReportReason): Int =
    when (reason) {
        ReportReason.CHILD_SAFETY -> R.string.hub_report_reason_child_safety
        ReportReason.PERSONAL_INFO -> R.string.hub_report_reason_personal_info
        ReportReason.ABUSIVE -> R.string.hub_report_reason_abusive
        ReportReason.FAKE -> R.string.hub_report_reason_fake
        ReportReason.MISLEADING -> R.string.hub_report_reason_misleading
        ReportReason.OTHER -> R.string.hub_report_reason_other
    }
