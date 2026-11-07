package com.shikkhokplus.app.feature.mfa.ui

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.net.Uri
import android.os.PersistableBundle
import android.view.WindowManager
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.DestructiveButton
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.OtpField
import com.shikkhokplus.app.core.designsystem.OtpFieldState
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dateTimeLabel
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.mfa.MfaFlow
import com.shikkhokplus.app.feature.mfa.MfaStatus
import com.shikkhokplus.app.feature.mfa.MfaStatusUiState
import com.shikkhokplus.app.feature.mfa.MfaUiState

/** The status card: on or off, and what goes with it. */
const val TAG_TWO_STEP_STATUS: String = "two_step_status"

/** Turn on, on the status page. */
const val TAG_TWO_STEP_TURN_ON: String = "two_step_turn_on"

/** Turn off, on the status page and as the confirming button. */
const val TAG_TWO_STEP_TURN_OFF: String = "two_step_turn_off"

/** New recovery codes, on the status page. */
const val TAG_TWO_STEP_NEW_CODES: String = "two_step_new_codes"

/** The few-codes-left warning. */
const val TAG_TWO_STEP_LOW: String = "two_step_low"

/** The "Required for your account" line. */
const val TAG_TWO_STEP_REQUIRED: String = "two_step_required"

/** The "Recommended for your account" line. */
const val TAG_TWO_STEP_RECOMMENDED: String = "two_step_recommended"

/** Open authenticator app. */
const val TAG_TWO_STEP_OPEN_APP: String = "two_step_open_app"

/** The no-app-found message. */
const val TAG_TWO_STEP_NO_APP: String = "two_step_no_app"

/** The setup key, in groups of four. */
const val TAG_TWO_STEP_SECRET: String = "two_step_secret"

/** Copy, beside the setup key. */
const val TAG_TWO_STEP_COPY_SECRET: String = "two_step_copy_secret"

/** One recovery code. */
const val TAG_TWO_STEP_CODE: String = "two_step_code"

/** Copy all, under the recovery codes. */
const val TAG_TWO_STEP_COPY_CODES: String = "two_step_copy_codes"

/** I've saved them. */
const val TAG_TWO_STEP_SAVED: String = "two_step_saved"

/** A write's refusal. */
const val TAG_TWO_STEP_ERROR: String = "two_step_error"

/** The retry after a failed write. */
const val TAG_TWO_STEP_RETRY: String = "two_step_retry"

/** The recovery-code field, when turning off. */
const val TAG_TWO_STEP_RECOVERY: String = "two_step_recovery"

/** The switch between an app code and a recovery code. */
const val TAG_TWO_STEP_TOGGLE: String = "two_step_toggle"

/** Cancel, in every step that can be left. */
const val TAG_TWO_STEP_CANCEL: String = "two_step_cancel"

/** The step that asks the server for a setup key, while it is in flight. */
const val TAG_TWO_STEP_STARTING: String = "two_step_starting"

/**
 * What each control on the two-step verification screen does.
 *
 * Bundled for the reason `SessionBinding` is: a dozen positional
 * callbacks cannot be read at the call site.
 *
 * @property onBack Leaves the screen
 * @property onRetry Reads the status again after a failure
 * @property onTurnOn Starts turning it on, and retries that start
 * @property onType Called with a code field as typed
 * @property onOpenAuthenticator Opens the `otpauth://` link in an app
 * @property onConfirm Sends the first code, and retries it
 * @property onStartTurnOff Starts turning it off
 * @property onToggleRecovery Switches between an app code and a recovery code
 * @property onTurnOff Sends the code that turns it off, and retries it
 * @property onStartNewCodes Starts making new recovery codes
 * @property onRenew Sends the code that makes them, and retries it
 * @property onFinishCodes Leaves the recovery codes once saved
 * @property onCancel Leaves the step in progress
 */
data class TwoStepActions(
    val onBack: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onTurnOn: () -> Unit = {},
    val onType: (String) -> Unit = {},
    val onOpenAuthenticator: (String) -> Unit = {},
    val onConfirm: () -> Unit = {},
    val onStartTurnOff: () -> Unit = {},
    val onToggleRecovery: () -> Unit = {},
    val onTurnOff: () -> Unit = {},
    val onStartNewCodes: () -> Unit = {},
    val onRenew: () -> Unit = {},
    val onFinishCodes: () -> Unit = {},
    val onCancel: () -> Unit = {},
)

/**
 * Two-step verification, reached from More for every role [0028]: where
 * it stands, and the steps that turn it on, make new recovery codes and
 * turn it off.
 *
 * **One screen, one step at a time.** The status page is the base; each
 * step is drawn in its place and Back leaves the step rather than the
 * screen, so a half-finished setup is never one tap from the menu.
 * Recovery codes are left only by "I've saved them" or Back, both of
 * which drop them for good.
 *
 * **No QR code.** The authenticator app is on this same phone, so the
 * `otpauth://` link opens it directly, and the setup key can be copied
 * or typed in by hand. A QR code would be for a second device, and would
 * need a library this app does not carry.
 *
 * @param state What to render
 * @param actions What each control does
 * @param modifier The layout modifier
 */
@Composable
fun TwoStepScreen(
    state: MfaUiState,
    actions: TwoStepActions,
    modifier: Modifier = Modifier,
) {
    val flow = state.flow
    val leaveStep = if (flow is MfaFlow.Codes) actions.onFinishCodes else actions.onCancel
    BackHandler(enabled = flow != MfaFlow.None, onBack = leaveStep)

    ScreenScaffold(
        title = stringResource(titleOf(flow)),
        modifier = modifier,
        onBack = if (flow == MfaFlow.None) actions.onBack else leaveStep,
    ) {
        when (flow) {
            MfaFlow.None -> StatusPage(state.status, actions)
            is MfaFlow.Starting -> StartingStep(flow, actions)
            is MfaFlow.Confirming -> ConfirmingStep(flow, actions)
            is MfaFlow.Codes -> CodesStep(flow, actions)
            is MfaFlow.TurningOff -> TurningOffStep(flow, actions)
            is MfaFlow.Renewing -> RenewingStep(flow, actions)
        }
    }
}

/**
 * The heading for each step.
 *
 * @param flow The step in progress
 * @return Its string resource
 */
private fun titleOf(flow: MfaFlow): Int =
    when (flow) {
        MfaFlow.None -> R.string.two_step_title
        is MfaFlow.Starting, is MfaFlow.Confirming -> R.string.two_step_setup_title
        is MfaFlow.Codes -> if (flow.renewed) R.string.two_step_codes_new_title else R.string.two_step_codes_title
        is MfaFlow.TurningOff -> R.string.two_step_off_title
        is MfaFlow.Renewing -> R.string.two_step_new_codes
    }

/**
 * The status page: what it does, where it stands, and the actions.
 *
 * @param status The status read
 * @param actions What each control does
 */
@Composable
private fun StatusPage(status: MfaStatusUiState, actions: TwoStepActions) {
    when (status) {
        MfaStatusUiState.Loading -> SkeletonList(rows = 2)
        is MfaStatusUiState.Failed ->
            ErrorCard(
                title = stringResource(MessageKeys.resolve(status.messageKey)),
                body = null,
                retryLabel = if (status.retryable) stringResource(R.string.auth_retry) else null,
                onRetry = if (status.retryable) actions.onRetry else null,
            )
        is MfaStatusUiState.Loaded -> Loaded(status.status, actions)
    }
}

/**
 * The status card and the actions it allows.
 *
 * @param status Where it stands
 * @param actions What each control does
 */
@Composable
private fun Loaded(status: MfaStatus, actions: TwoStepActions) {
    Text(stringResource(R.string.two_step_intro), style = MaterialTheme.typography.bodyMedium)
    StatusCard(status)
    if (status.lowOnCodes) {
        Banner(
            title = stringResource(R.string.two_step_codes_low_title),
            body = stringResource(R.string.two_step_codes_low_body),
            tone = BannerTone.ERROR,
            modifier = Modifier.testTag(TAG_TWO_STEP_LOW),
        )
    }
    if (status.enabled) {
        SecondaryButton(
            text = stringResource(R.string.two_step_new_codes),
            onClick = actions.onStartNewCodes,
            modifier = Modifier.fillMaxWidth().testTag(TAG_TWO_STEP_NEW_CODES),
        )
    } else {
        PrimaryButton(
            text = stringResource(R.string.two_step_turn_on),
            onClick = actions.onTurnOn,
            modifier = Modifier.fillMaxWidth().testTag(TAG_TWO_STEP_TURN_ON),
        )
    }
    if (status.canTurnOff) {
        DestructiveButton(
            text = stringResource(R.string.two_step_turn_off),
            onClick = actions.onStartTurnOff,
            modifier = Modifier.fillMaxWidth().testTag(TAG_TWO_STEP_TURN_OFF),
        )
    }
}

/**
 * On or off, when it was turned on, whether it is required or
 * recommended, and how many recovery codes are left.
 *
 * @param status Where it stands
 */
@Composable
private fun StatusCard(status: MfaStatus) {
    val colors = MaterialTheme.colorScheme
    ShikkhokCard(modifier = Modifier.testTag(TAG_TWO_STEP_STATUS)) {
        Text(
            stringResource(if (status.enabled) R.string.two_step_status_on else R.string.two_step_status_off),
            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
            color = if (status.enabled) colors.primary else colors.onSurface,
        )
        status.enabledAt?.let {
            Text(
                stringResource(R.string.two_step_on_since, dateTimeLabel(it)),
                style = MaterialTheme.typography.bodySmall,
                color = colors.onSurfaceVariant,
            )
        }
        if (status.required) {
            Text(
                stringResource(R.string.two_step_required),
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.testTag(TAG_TWO_STEP_REQUIRED),
            )
        }
        if (status.showRecommended) {
            Text(
                stringResource(R.string.two_step_recommended_note),
                style = MaterialTheme.typography.labelLarge,
                color = colors.primary,
                modifier = Modifier.testTag(TAG_TWO_STEP_RECOMMENDED),
            )
        }
        if (status.enabled) {
            Text(
                pluralStringResource(
                    R.plurals.two_step_codes_left,
                    status.recoveryCodesLeft,
                    Numerals.count(status.recoveryCodesLeft),
                ),
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

/**
 * Asking the server for a setup key: a loader, or why it failed.
 *
 * @param flow The step
 * @param actions What each control does
 */
@Composable
private fun StartingStep(flow: MfaFlow.Starting, actions: TwoStepActions) {
    if (flow.write == WriteState.Saving) {
        LogoLoader(
            modifier = Modifier.testTag(TAG_TWO_STEP_STARTING),
            size = 72.dp,
            label = stringResource(R.string.two_step_starting),
        )
    }
    WriteFailure(flow.write, actions.onTurnOn)
    Cancel(actions.onCancel)
}

/**
 * The setup key, the button that opens the authenticator app, and the
 * first code, which confirms it.
 *
 * @param flow The step
 * @param actions What each control does
 */
@Composable
private fun ConfirmingStep(flow: MfaFlow.Confirming, actions: TwoStepActions) {
    val context = LocalContext.current
    Text(stringResource(R.string.two_step_setup_step1), style = MaterialTheme.typography.bodyMedium)
    PrimaryButton(
        text = stringResource(R.string.two_step_open_app),
        onClick = { actions.onOpenAuthenticator(flow.otpauthUri) },
        modifier = Modifier.fillMaxWidth().testTag(TAG_TWO_STEP_OPEN_APP),
    )
    if (flow.noAuthenticator) {
        Banner(
            title = stringResource(R.string.two_step_no_app),
            tone = BannerTone.NEUTRAL,
            modifier = Modifier.testTag(TAG_TWO_STEP_NO_APP),
        )
    }
    Text(stringResource(R.string.two_step_key_label), style = MaterialTheme.typography.labelLarge)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(
            flow.secretGroups,
            style = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Monospace),
            modifier = Modifier.weight(1f).testTag(TAG_TWO_STEP_SECRET),
        )
        TextAction(
            text = stringResource(R.string.two_step_copy),
            onClick = { copySensitive(context, flow.secret) },
            modifier = Modifier.testTag(TAG_TWO_STEP_COPY_SECRET),
        )
    }
    Text(stringResource(R.string.two_step_setup_step2), style = MaterialTheme.typography.bodyMedium)
    CodeBoxes(flow.code, flow.write, actions.onType, actions.onConfirm)
    WriteFailure(flow.write, actions.onConfirm)
    Cancel(actions.onCancel)
}

/**
 * The recovery codes, shown once, with Copy all and "I've saved them".
 *
 * **The window is secure while they are on screen**: no screenshot, no
 * screen recording, and a blank thumbnail in Recents, so the codes are
 * not kept anywhere the person did not choose to put them.
 *
 * @param flow The step
 * @param actions What each control does
 */
@Composable
private fun CodesStep(flow: MfaFlow.Codes, actions: TwoStepActions) {
    SecureWindow()
    val context = LocalContext.current
    if (flow.renewed) {
        Banner(title = stringResource(R.string.two_step_codes_old_stopped), tone = BannerTone.NEUTRAL)
    }
    Text(stringResource(R.string.two_step_codes_body), style = MaterialTheme.typography.bodyMedium)
    Text(
        stringResource(R.string.two_step_codes_once),
        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
        color = MaterialTheme.colorScheme.error,
    )
    ShikkhokCard {
        flow.codes.forEach { code ->
            Text(
                code,
                style = MaterialTheme.typography.titleMedium.copy(fontFamily = FontFamily.Monospace),
                modifier = Modifier.padding(vertical = 2.dp).testTag(TAG_TWO_STEP_CODE),
            )
        }
    }
    SecondaryButton(
        text = stringResource(R.string.two_step_copy_all),
        onClick = { copySensitive(context, flow.codes.joinToString("\n")) },
        modifier = Modifier.fillMaxWidth().testTag(TAG_TWO_STEP_COPY_CODES),
    )
    PrimaryButton(
        text = stringResource(R.string.two_step_saved),
        onClick = actions.onFinishCodes,
        modifier = Modifier.fillMaxWidth().testTag(TAG_TWO_STEP_SAVED),
    )
}

/**
 * Turning it off: an app code in the boxes, or a recovery code in a
 * field with its own button.
 *
 * @param flow The step
 * @param actions What each control does
 */
@Composable
private fun TurningOffStep(flow: MfaFlow.TurningOff, actions: TwoStepActions) {
    Text(
        stringResource(if (flow.useRecovery) R.string.two_step_off_recovery_body else R.string.two_step_off_body),
        style = MaterialTheme.typography.bodyMedium,
    )
    if (flow.useRecovery) {
        ShikkhokTextField(
            value = flow.input,
            onValueChange = actions.onType,
            label = stringResource(R.string.two_step_recovery_label),
            enabled = flow.write != WriteState.Saving,
            keyboardOptions =
                KeyboardOptions(
                    keyboardType = KeyboardType.Ascii,
                    capitalization = KeyboardCapitalization.Characters,
                    autoCorrectEnabled = false,
                ),
            fieldModifier = Modifier.testTag(TAG_TWO_STEP_RECOVERY),
        )
        DestructiveButton(
            text = stringResource(R.string.two_step_turn_off),
            onClick = actions.onTurnOff,
            enabled = flow.canSubmit,
            modifier = Modifier.fillMaxWidth().testTag(TAG_TWO_STEP_TURN_OFF),
        )
    } else {
        CodeBoxes(flow.input, flow.write, actions.onType, actions.onTurnOff)
    }
    WriteFailure(flow.write, actions.onTurnOff)
    if (flow.write != WriteState.Saving) {
        TextAction(
            text = stringResource(if (flow.useRecovery) R.string.two_step_use_app else R.string.two_step_use_recovery),
            onClick = actions.onToggleRecovery,
            modifier = Modifier.testTag(TAG_TWO_STEP_TOGGLE),
        )
    }
    Cancel(actions.onCancel)
}

/**
 * New recovery codes: the app code that makes them.
 *
 * @param flow The step
 * @param actions What each control does
 */
@Composable
private fun RenewingStep(flow: MfaFlow.Renewing, actions: TwoStepActions) {
    Text(stringResource(R.string.two_step_renew_body), style = MaterialTheme.typography.bodyMedium)
    CodeBoxes(flow.code, flow.write, actions.onType, actions.onRenew)
    WriteFailure(flow.write, actions.onRenew)
    Cancel(actions.onCancel)
}

/**
 * Six boxes for an app code, which send it on the sixth digit -- the
 * same control as signing in -- with the checking overlay while it is
 * with the server.
 *
 * @param code The digits typed
 * @param write Where the request stands
 * @param onType Called with the digits
 * @param onComplete Called on the sixth digit
 */
@Composable
private fun CodeBoxes(code: String, write: WriteState, onType: (String) -> Unit, onComplete: () -> Unit) {
    val saving = write == WriteState.Saving
    OtpField(
        code = code,
        onCodeChange = onType,
        onComplete = onComplete,
        state =
            when (write) {
                WriteState.Saving -> OtpFieldState.CHECKING
                is WriteState.Failed -> OtpFieldState.WRONG
                else -> OtpFieldState.EDITING
            },
        enabled = !saving,
        modifier = Modifier.fillMaxWidth(),
    )
    if (saving) {
        LogoLoader(size = 72.dp, label = stringResource(R.string.auth_checking_code))
    }
}

/**
 * A refused or unanswered write: the server's reason, and a retry when
 * it says one can help. Draws nothing for any other write state.
 *
 * @param write Where the request stands
 * @param onRetry Called to send again
 */
@Composable
private fun WriteFailure(write: WriteState, onRetry: () -> Unit) {
    val failed = write as? WriteState.Failed ?: return
    Banner(
        title = stringResource(MessageKeys.resolve(failed.messageKey)),
        tone = BannerTone.ERROR,
        modifier = Modifier.testTag(TAG_TWO_STEP_ERROR),
    )
    if (failed.retryable) {
        SecondaryButton(
            text = stringResource(R.string.auth_retry),
            onClick = onRetry,
            modifier = Modifier.fillMaxWidth().testTag(TAG_TWO_STEP_RETRY),
        )
    }
}

/**
 * Leave the step without finishing it.
 *
 * @param onCancel Called when tapped
 */
@Composable
private fun Cancel(onCancel: () -> Unit) {
    TextAction(
        text = stringResource(R.string.action_cancel),
        onClick = onCancel,
        modifier = Modifier.testTag(TAG_TWO_STEP_CANCEL),
    )
}

/** Keep the window out of screenshots, recordings and Recents while composed. */
@Composable
private fun SecureWindow() {
    val activity = LocalContext.current.findActivity()
    DisposableEffect(activity) {
        val window = activity?.window
        window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        onDispose { window?.clearFlags(WindowManager.LayoutParams.FLAG_SECURE) }
    }
}

/**
 * The activity a composition is hosted in, through any wrappers.
 *
 * @return The activity, or null when there is none
 */
private tailrec fun Context.findActivity(): Activity? =
    when (this) {
        is Activity -> this
        is ContextWrapper -> baseContext.findActivity()
        else -> null
    }

/**
 * Copy a secret to the clipboard, marked sensitive so the keyboard's
 * clipboard preview and the system's copy confirmation do not show it.
 *
 * @param context Any context
 * @param text What to copy
 */
internal fun copySensitive(context: Context, text: String) {
    val clipboard = context.getSystemService(ClipboardManager::class.java) ?: return
    val clip = ClipData.newPlainText(CLIP_LABEL, text)
    clip.description.extras = PersistableBundle().apply { putBoolean(EXTRA_IS_SENSITIVE, true) }
    clipboard.setPrimaryClip(clip)
}

/**
 * Open an `otpauth://` link in whichever authenticator app handles it.
 *
 * @param context The activity context
 * @param uri The link the server sent
 * @return False when no app on this phone opens it
 */
internal fun openAuthenticator(context: Context, uri: String): Boolean =
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(uri)))
        true
    } catch (_: ActivityNotFoundException) {
        false
    }

/** The clipboard entry's label; not shown to the person. */
private const val CLIP_LABEL = "ShikkhokPlus"

/**
 * `ClipDescription.EXTRA_IS_SENSITIVE`, spelled out because the constant
 * arrived in API 33 and the flag is read, harmlessly ignored, below it.
 */
private const val EXTRA_IS_SENSITIVE = "android.content.extra.IS_SENSITIVE"
