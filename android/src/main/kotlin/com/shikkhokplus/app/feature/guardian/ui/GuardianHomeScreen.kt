package com.shikkhokplus.app.feature.guardian.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.guardian.GuardianChild
import com.shikkhokplus.app.feature.guardian.GuardianUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_GUARDIAN_LOADING: String = "guardian_loading"

/** The screen heading. */
const val TAG_GUARDIAN_TITLE: String = "guardian_title"

/** The child currently being shown. */
const val TAG_GUARDIAN_SELECTED: String = "guardian_selected"

/**
 * The displayed child's NAME alone.
 *
 * Separate from the block above so a test can assert **who is being
 * shown** rather than who is on screen: every child's name also appears
 * on its own switcher chip.
 */
const val TAG_GUARDIAN_SELECTED_NAME: String = "guardian_selected_name"

/**
 * The switcher row. **Absent in the one-child case**, which is what the
 * separate states exist to make testable.
 */
const val TAG_GUARDIAN_SWITCHER: String = "guardian_switcher"

/** One child's chip inside the switcher. */
const val TAG_GUARDIAN_CHIP: String = "guardian_chip"

/** The explanation shown when a guardian reaches nothing. */
const val TAG_GUARDIAN_EMPTY: String = "guardian_empty"

/** The error message. */
const val TAG_GUARDIAN_ERROR: String = "guardian_error"

/** The retry control, shown only when the server said retryable. */
const val TAG_GUARDIAN_RETRY: String = "guardian_retry"

/**
 * A guardian's children, and the switcher between them [`G1`, US2.6].
 *
 * **The switch is a SELECTION within this screen, never a navigation
 * push** [BR4.2, NFR14.30, AC9.4.2]. `onSelectChild` replaces the
 * selected child in the state this composable is handed; nothing is
 * stacked and no destination is pushed, so Back cannot land on the
 * previous child's data. That is a privacy case wearing navigation's
 * clothes: two scopes of one lens are adjacent here and nowhere else in
 * D2, and no server-side control can observe a failure — both requests
 * are legitimately authorized and neither response is anomalous.
 *
 * It is also why this screen takes no `NavController` and owns no back
 * stack. The obligation is satisfiable precisely because there is
 * nothing here that could push.
 *
 * **Renders a [GuardianUiState] and nothing else.** No `children.size`
 * comparison chooses the switcher — the one-child and several-children
 * cases are separate states the mapper decided between.
 *
 * @param state What to render
 * @param onSelectChild Called with the child to show instead
 * @param onRetry Called when the user asks to retry
 * @param modifier The layout modifier
 */
@Composable
fun GuardianHomeScreen(
    state: GuardianUiState,
    onSelectChild: (GuardianChild) -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.guardian_home_title),
        modifier = modifier,
    ) {
        Text(
            stringResource(R.string.guardian_home_title),
            Modifier.testTag(TAG_GUARDIAN_TITLE),
            style = MaterialTheme.typography.titleLarge,
        )

        when (state) {
            GuardianUiState.Idle -> Unit

            GuardianUiState.Loading ->
                CircularProgressIndicator(Modifier.testTag(TAG_GUARDIAN_LOADING))

            // **No switcher drawn.** There is nothing to switch
            // between, and a control offering one option is noise.
            is GuardianUiState.OneChild -> SelectedChild(state.child)

            is GuardianUiState.SeveralChildren -> {
                Text(stringResource(R.string.guardian_switch_label))
                Row(
                    Modifier.testTag(TAG_GUARDIAN_SWITCHER),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    state.children.forEach { child ->
                        FilterChip(
                            // **A selection control, not a link.** It
                            // reports which child was chosen and the
                            // state replaces; it navigates nowhere.
                            selected = child == state.selected,
                            onClick = { onSelectChild(child) },
                            label = { Text(Numerals.freeText(child.displayName)) },
                            modifier = Modifier.testTag(TAG_GUARDIAN_CHIP),
                        )
                    }
                }
                SelectedChild(state.selected)
            }

            GuardianUiState.Empty -> {
                Text(
                    stringResource(R.string.guardian_empty_title),
                    Modifier.testTag(TAG_GUARDIAN_EMPTY),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(stringResource(R.string.guardian_empty_body))
            }

            is GuardianUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_GUARDIAN_ERROR),
                )
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_GUARDIAN_RETRY),
                    ) {
                        Text(stringResource(R.string.roster_retry))
                    }
                }
            }
        }
    }
}

/**
 * The child currently being shown.
 *
 * Names the batch alongside the child **even in the single-child case**
 * [AC2.8.5]: that is where attribution is most needed, because there is
 * no selection list to have shown it.
 *
 * @param child The child being shown
 */
@Composable
private fun SelectedChild(child: GuardianChild) {
    Column(Modifier.fillMaxWidth().testTag(TAG_GUARDIAN_SELECTED)) {
        Text(
            // Text a teacher typed, shown exactly as typed.
            text = Numerals.freeText(child.displayName),
            style = MaterialTheme.typography.titleMedium,
            // Tagged separately from the block, so a test can read WHO
            // is being displayed rather than who is merely on screen:
            // every child's name appears in the switcher too, and a
            // bare text query would find the chip.
            modifier = Modifier.testTag(TAG_GUARDIAN_SELECTED_NAME),
        )
        Text(
            text = stringResource(
                R.string.guardian_child_in_batch,
                Numerals.freeText(child.batchName),
                Numerals.freeText(child.teacherDisplayName.orEmpty()),
            ),
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
