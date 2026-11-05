package com.shikkhokplus.app.feature.students.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SkeletonBlock
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.students.StudentListRow
import com.shikkhokplus.app.feature.students.StudentsUiState

/** One student in the picker. Not user-visible text. */
const val TAG_PICK_ROW: String = "pick_row"

/** "Add N". */
const val TAG_PICK_ADD: String = "pick_add"

/** "New student". */
const val TAG_PICK_NEW: String = "pick_new"

/**
 * What the picker can be asked to do.
 *
 * @property onBack Called to leave
 * @property onToggle Called with a student id to choose or unchoose it
 * @property onSearch Called with the search text
 * @property onAdd Called to seat the chosen students
 * @property onNew Called to add a student who is not on the list yet
 * @property onRetry Called when the teacher asks to retry
 */
data class PickStudentsActions(
    val onBack: () -> Unit,
    val onToggle: (String) -> Unit,
    val onSearch: (String) -> Unit,
    val onAdd: () -> Unit,
    val onNew: () -> Unit,
    val onRetry: () -> Unit,
)

/**
 * Add existing students to one batch, or start a new one.
 *
 * The list is the server's: the teacher's students NOT already in this
 * batch. "New student" opens the add form with this batch chosen.
 *
 * @param batchName The batch, for the title
 * @param state The students on offer
 * @param query The search text
 * @param picked The chosen students
 * @param saving True while the add is in flight
 * @param error Why the last add was refused, resolved, or null
 * @param actions What the picker can be asked to do
 * @param modifier The layout modifier
 */
@Composable
fun PickStudentsScreen(
    batchName: String,
    state: StudentsUiState,
    query: String,
    picked: Set<String>,
    saving: Boolean,
    error: String?,
    actions: PickStudentsActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.pick_students_title, Numerals.freeText(batchName)),
        onBack = actions.onBack,
        modifier = modifier,
    ) {
        OutlinedTextField(
            value = query,
            onValueChange = actions.onSearch,
            placeholder = { Text(stringResource(R.string.students_search)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        when (state) {
            StudentsUiState.Loading -> SkeletonBlock(widthFraction = 0.6f, height = 16.dp)
            is StudentsUiState.Empty ->
                Text(
                    text = stringResource(R.string.pick_students_empty),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            is StudentsUiState.Failed ->
                EmptyState(
                    title = stringResource(R.string.students_error_title),
                    body = stringResource(MessageKeys.resolve(state.messageKey)),
                ) {
                    if (state.retryable) {
                        OutlinedButton(onClick = actions.onRetry) { Text(stringResource(R.string.roster_retry)) }
                    }
                }
            is StudentsUiState.Loaded ->
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    state.rows.forEach { row -> PickRow(row, row.id in picked) { actions.onToggle(row.id) } }
                }
        }
        error?.let {
            Text(text = it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = actions.onNew,
                modifier = Modifier.weight(1f).heightIn(min = Reach.touch).testTag(TAG_PICK_NEW),
            ) {
                Text(stringResource(R.string.pick_students_new))
            }
            Button(
                onClick = actions.onAdd,
                enabled = picked.isNotEmpty() && !saving,
                modifier = Modifier.weight(1f).heightIn(min = Reach.touch).testTag(TAG_PICK_ADD),
            ) {
                Text(stringResource(R.string.pick_students_add, Numerals.count(picked.size)))
            }
        }
    }
}

/**
 * One student with a checkbox, and the batches they already sit in.
 *
 * @param row The student
 * @param checked Whether chosen
 * @param onToggle Called when tapped
 */
@Composable
private fun PickRow(row: StudentListRow, checked: Boolean, onToggle: () -> Unit) {
    Row(
        modifier =
            Modifier
                .fillMaxWidth()
                .heightIn(min = Reach.touch)
                .toggleable(value = checked, role = Role.Checkbox, onValueChange = { onToggle() })
                .padding(vertical = 4.dp)
                .testTag(TAG_PICK_ROW),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Checkbox(checked = checked, onCheckedChange = null)
        Column {
            Text(text = Numerals.freeText(row.name), style = MaterialTheme.typography.bodyMedium)
            Text(
                text =
                    if (row.batchNames.isEmpty()) {
                        stringResource(R.string.students_not_in_batch)
                    } else {
                        row.batchNames.joinToString(" · ") { Numerals.freeText(it) }
                    },
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
