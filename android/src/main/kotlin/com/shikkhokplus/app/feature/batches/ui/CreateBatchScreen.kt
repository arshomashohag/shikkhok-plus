package com.shikkhokplus.app.feature.batches.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.core.network.ScheduleSlotDto
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.ui.BatchCreateForm
import com.shikkhokplus.app.feature.auth.MessageKeys

/** Stable test identifiers. Not user-visible text. */
const val TAG_CREATE_BATCH_FORM: String = "create_batch_form"

/** The in-flight indicator. */
const val TAG_CREATE_BATCH_SUBMITTING: String = "create_batch_submitting"

/** The server's refusal. */
const val TAG_CREATE_BATCH_ERROR: String = "create_batch_error"

/** The retry control, shown only when the server said retryable. */
const val TAG_CREATE_BATCH_RETRY: String = "create_batch_retry"

/** The confirmation shown once the class exists. */
const val TAG_CREATE_BATCH_CREATED: String = "create_batch_created"

/**
 * What the create-batch screen is showing.
 *
 * Four states, named rather than derived from nullable fields: a screen
 * reading `if (error != null && !submitting)` to decide what to draw is
 * reconstructing a state machine from its symptoms.
 */
sealed interface CreateBatchUiState {
    /** The form, awaiting input. */
    data object Form : CreateBatchUiState

    /** The request is in flight. */
    data object Submitting : CreateBatchUiState

    /**
     * The server refused.
     *
     * @property messageKey Names a string resource, never English text
     *   from the server [TC-15, D-43]
     * @property retryable Read from the envelope, never inferred [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : CreateBatchUiState

    /**
     * The class exists.
     *
     * @property batchName What it was called
     */
    data class Created(val batchName: String) : CreateBatchUiState
}

/**
 * Create a class [US2.1, W1].
 *
 * **Renders a [CreateBatchUiState] and nothing else.** The only
 * conditional here is `state.retryable`, which the server set — not a
 * comparison of any domain value [TC-9, D-31].
 *
 * **Client validation is FORMAT only** [team: Layer boundaries]. The
 * submit button is disabled until a name exists, which spares the
 * teacher a round trip to learn a field is blank, and the server
 * rejects a blank name too. Whether this teacher *may* create a class
 * is a server decision and arrives as [CreateBatchUiState.Failed].
 *
 * @param state What to render
 * @param onCreate Called with the entered values
 * @param onCancel Called when the teacher backs out
 * @param onRetry Called when the user asks to retry
 * @param onDone Called when the teacher leaves the confirmation
 * @param modifier The layout modifier
 */
@Composable
fun CreateBatchScreen(
    state: CreateBatchUiState,
    onCreate: (String, List<String>, String?, Int?, List<ScheduleSlotDto>) -> Unit,
    onCancel: () -> Unit,
    onRetry: () -> Unit = {},
    onDone: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.screen_title_create_batch),
        modifier = modifier,
    ) {
        when (state) {
            CreateBatchUiState.Form ->
                BatchCreateForm(
                    onCreate = onCreate,
                    onCancel = onCancel,
                    modifier = Modifier.testTag(TAG_CREATE_BATCH_FORM),
                )

            CreateBatchUiState.Submitting -> {
                LogoLoader(
                    Modifier.testTag(TAG_CREATE_BATCH_SUBMITTING),
                    label = stringResource(R.string.batch_create_submitting),
                )
            }

            is CreateBatchUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_CREATE_BATCH_ERROR),
                )
                // **Only when the server said retryable** [TC-9]. A
                // retry on a non-retryable refusal invites the teacher
                // to repeat something that cannot work.
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_CREATE_BATCH_RETRY),
                    ) {
                        Text(stringResource(R.string.roster_retry))
                    }
                }
            }

            is CreateBatchUiState.Created -> {
                Text(
                    stringResource(R.string.batch_create_created),
                    Modifier.testTag(TAG_CREATE_BATCH_CREATED),
                    style = MaterialTheme.typography.titleMedium,
                )
                Button(onClick = onDone) {
                    Text(stringResource(R.string.action_close))
                }
            }
        }
    }
}
