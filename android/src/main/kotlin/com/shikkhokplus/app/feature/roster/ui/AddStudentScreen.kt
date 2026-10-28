package com.shikkhokplus.app.feature.roster.ui

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
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.ui.StudentAddForm
import com.shikkhokplus.app.feature.auth.MessageKeys

/** Stable test identifiers. Not user-visible text. */
const val TAG_ADD_STUDENT_FORM: String = "add_student_form"

/** The in-flight indicator. */
const val TAG_ADD_STUDENT_SUBMITTING: String = "add_student_submitting"

/** The server's refusal, including the duplicate case. */
const val TAG_ADD_STUDENT_ERROR: String = "add_student_error"

/** The retry control, shown only when the server said retryable. */
const val TAG_ADD_STUDENT_RETRY: String = "add_student_retry"

/** The confirmation shown once the seat exists. */
const val TAG_ADD_STUDENT_ADDED: String = "add_student_added"

/**
 * What the add-student screen is showing.
 *
 * Four states, matching `T8`'s specification: form, submitting, failed,
 * added.
 */
sealed interface AddStudentUiState {
    /** The form, awaiting input. */
    data object Form : AddStudentUiState

    /** The request is in flight. */
    data object Submitting : AddStudentUiState

    /**
     * The server refused.
     *
     * **A duplicate arrives here**, not as a client-side check
     * [frontend-components: Form validation]. Whether a number is
     * already on this batch is a server decision: the client does not
     * hold the roster of every batch and could not answer it, and a
     * client check with no server counterpart would be a business rule
     * living on the client.
     *
     * @property messageKey Names a string resource, never English text
     *   from the server [TC-15, D-43]
     * @property retryable Read from the envelope, never inferred [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : AddStudentUiState

    /**
     * The seat exists, and is **pending on both links** [ADR-013, W2].
     *
     * Nothing was sent to the person named [BR1.5, AC1.15.4]. They
     * discover the seat when they sign in, and the teacher is told
     * nothing further — which is why this confirmation says the seat
     * was added rather than that anyone was invited.
     *
     * @property displayName The teacher-typed name for the new seat
     */
    data class Added(val displayName: String) : AddStudentUiState
}

/**
 * Add a student to a class [`T8`, US2.2].
 *
 * **Renders an [AddStudentUiState] and nothing else.** The only
 * conditional is `state.retryable`, which the server set [TC-9, D-31].
 *
 * **An empty fee field means INHERIT, not zero** [AC2.2.5], which the
 * shared form already enforces by sending null when blank: zero is a
 * waiver, and defaulting to it would silently waive every fee.
 *
 * @param state What to render
 * @param onAdd Called with the entered values
 * @param onCancel Called when the teacher backs out
 * @param onRetry Called when the user asks to retry
 * @param onDone Called when the teacher leaves the confirmation
 * @param modifier The layout modifier
 */
@Composable
fun AddStudentScreen(
    state: AddStudentUiState,
    onAdd: (String, String, String?, String?) -> Unit,
    onCancel: () -> Unit,
    onRetry: () -> Unit = {},
    onDone: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.screen_title_add_student),
        modifier = modifier,
    ) {
        when (state) {
            AddStudentUiState.Form -> {
                StudentAddForm(
                    onAdd = onAdd,
                    onCancel = onCancel,
                    modifier = Modifier.testTag(TAG_ADD_STUDENT_FORM),
                )
                Text(stringResource(R.string.student_add_guardian_hint))
            }

            AddStudentUiState.Submitting -> {
                LogoLoader(
                    Modifier.testTag(TAG_ADD_STUDENT_SUBMITTING),
                )
                Text(stringResource(R.string.student_add_submitting))
            }

            is AddStudentUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_ADD_STUDENT_ERROR),
                )
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_ADD_STUDENT_RETRY),
                    ) {
                        Text(stringResource(R.string.roster_retry))
                    }
                }
            }

            is AddStudentUiState.Added -> {
                Text(
                    stringResource(R.string.student_add_added),
                    Modifier.testTag(TAG_ADD_STUDENT_ADDED),
                    style = MaterialTheme.typography.titleMedium,
                )
                Button(onClick = onDone) {
                    Text(stringResource(R.string.action_close))
                }
            }
        }
    }
}
