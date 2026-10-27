package com.shikkhokplus.app.feature.marks.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LogoLoader
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.MarkRow
import com.shikkhokplus.app.feature.marks.MarksUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_MARK_ENTRY_LOADING: String = "mark_entry_loading"

/** The exam heading. */
const val TAG_MARK_ENTRY_TITLE: String = "mark_entry_title"

/** The list of seats. */
const val TAG_MARK_ENTRY_LIST: String = "mark_entry_list"

/** One seat. */
const val TAG_MARK_ENTRY_ROW: String = "mark_entry_row"

/** One seat's mark field. */
const val TAG_MARK_ENTRY_FIELD: String = "mark_entry_field"

/** One seat's mark-absent action. */
const val TAG_MARK_ENTRY_ABSENT: String = "mark_entry_absent"

/** One seat's result state. */
const val TAG_MARK_ENTRY_STATE: String = "mark_entry_state"

/** The notice shown on a seat that cannot be marked. */
const val TAG_MARK_ENTRY_LOCKED: String = "mark_entry_locked"

/** The notice shown when the exam accepts no write. */
const val TAG_MARK_ENTRY_READ_ONLY: String = "mark_entry_read_only"

/** The error message. */
const val TAG_MARK_ENTRY_ERROR: String = "mark_entry_error"

/** The retry button. */
const val TAG_MARK_ENTRY_RETRY: String = "mark_entry_retry"

/**
 * Mark entry for one exam [FR4.2, FR4.3].
 *
 * **This composable renders a [MarksUiState] and nothing else.** Three
 * decisions that look like presentation are all the mapper's: which
 * label a result state carries, whether a seat may be marked at all
 * (`joined_after` cannot [BR4.3]), and whether the exam accepts writes
 * [BR5.5].
 *
 * **The mark field's validation is format-only, never policy.** It
 * admits digits and nothing else; whether a number is within the exam's
 * total is the **server's** check [BR4.2], because that bound spans a
 * foreign key and a client holding it would diverge the moment an exam
 * is edited. Duplicated-then-diverging validation is one of the five
 * named erosion paths [team: Code Style].
 *
 * **An empty field is not a zero.** A zero is a mark the student
 * earned; an empty field is a mark nobody has entered, and collapsing
 * them tells a guardian their child scored nothing when nobody has
 * marked the paper [BR4.2].
 *
 * @param state What to render
 * @param onMark Called with the seat and the score the teacher entered
 * @param onAbsent Called with the seat the teacher marked absent
 * @param onRetry Called when the teacher asks to retry
 * @param modifier Layout modifier
 */
@Composable
fun MarkEntryScreen(
    state: MarksUiState,
    onMark: (MarkRow, Int) -> Unit = { _, _ -> },
    onAbsent: (MarkRow) -> Unit = {},
    onRetry: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    ListScreenScaffold(
        title = stringResource(R.string.screen_title_mark_entry),
        modifier = modifier,
    ) {
        when (state) {
            MarksUiState.Loading ->
                LogoLoader(Modifier.testTag(TAG_MARK_ENTRY_LOADING))

            is MarksUiState.EntryLoaded -> {
                Text(
                    stringResource(
                        R.string.mark_entry_title,
                        Numerals.freeText(state.examTitle),
                        Numerals.count(state.totalMarks),
                    ),
                    Modifier.testTag(TAG_MARK_ENTRY_TITLE),
                )

                if (!state.writable) {
                    Text(
                        stringResource(R.string.mark_entry_read_only),
                        Modifier.testTag(TAG_MARK_ENTRY_READ_ONLY),
                        color = MaterialTheme.colorScheme.error,
                    )
                }

                LazyColumn(Modifier.testTag(TAG_MARK_ENTRY_LIST)) {
                    items(state.rows, key = { it.enrollmentId }) { row ->
                        MarkRowView(row, onMark, onAbsent)
                    }
                }
            }

            is MarksUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_MARK_ENTRY_ERROR),
                )
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_MARK_ENTRY_RETRY),
                    ) {
                        Text(stringResource(R.string.mark_entry_retry))
                    }
                }
            }

            else -> Unit
        }
    }
}

/**
 * One seat's mark.
 *
 * @param row The seat
 * @param onMark Called with the score the teacher entered
 * @param onAbsent Called when the teacher marks the seat absent
 */
@Composable
private fun MarkRowView(
    row: MarkRow,
    onMark: (MarkRow, Int) -> Unit,
    onAbsent: (MarkRow) -> Unit,
) {
    // The typed text, held locally while the teacher types. Seeded
    // from the server's value so an existing mark is editable rather
    // than needing to be re-typed. A zero seeds as "0", because a zero
    // IS a mark [BR4.2].
    var typed by remember(row.enrollmentId, row.marks) {
        mutableStateOf(row.marks?.toString().orEmpty())
    }

    Column(Modifier.fillMaxWidth().testTag(TAG_MARK_ENTRY_ROW)) {
        Text(Numerals.freeText(row.displayName))
        Text(
            stringResource(MessageKeys.resolve(row.stateLabel)),
            Modifier.testTag(TAG_MARK_ENTRY_STATE),
        )

        // **`isEditable` is the mapper's decision** from the server's
        // state [BR4.3]. A seat that joined after the exam date cannot
        // be marked, and the client never compares those dates itself.
        if (!row.isEditable) {
            Text(
                stringResource(R.string.mark_entry_locked),
                Modifier.testTag(TAG_MARK_ENTRY_LOCKED),
            )
            return@Column
        }

        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedTextField(
                value = typed,
                onValueChange = { entered ->
                    // **Format-only.** Digits and nothing else. The
                    // RANGE is the server's check [BR4.2], and a
                    // client bound would diverge from it the moment an
                    // exam's total is edited.
                    if (entered.all(Char::isDigit)) {
                        typed = entered
                        entered.toIntOrNull()?.let { onMark(row, it) }
                    }
                },
                label = { Text(stringResource(R.string.mark_entry_label)) },
                singleLine = true,
                keyboardOptions =
                    KeyboardOptions(
                        keyboardType = KeyboardType.Number,
                        imeAction = ImeAction.Next,
                    ),
                modifier = Modifier.weight(1f).testTag(TAG_MARK_ENTRY_FIELD),
            )

            // **Absent is its own action, not an empty field.** An
            // empty field is a mark nobody has entered; absence is a
            // fact the teacher recorded [BR4.3].
            TextButton(
                onClick = { onAbsent(row) },
                modifier = Modifier.testTag(TAG_MARK_ENTRY_ABSENT),
            ) {
                Text(stringResource(R.string.mark_entry_absent))
            }
        }
    }
}
