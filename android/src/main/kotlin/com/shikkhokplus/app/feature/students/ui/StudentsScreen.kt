package com.shikkhokplus.app.feature.students.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonBlock
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.students.BatchOption
import com.shikkhokplus.app.feature.students.StudentFilter
import com.shikkhokplus.app.feature.students.StudentListRow
import com.shikkhokplus.app.feature.students.StudentsUiState

/** The list of students. Not user-visible text. */
const val TAG_STUDENTS_LIST: String = "students_list"

/** One student. */
const val TAG_STUDENT_ROW: String = "student_row"

/** The search field. */
const val TAG_STUDENTS_SEARCH: String = "students_search"

/** One filter chip. */
const val TAG_STUDENTS_FILTER: String = "students_filter"

/** The add-student button. */
const val TAG_STUDENTS_ADD: String = "students_add"

/** The empty state. */
const val TAG_STUDENTS_EMPTY: String = "students_empty"

/** The error state. */
const val TAG_STUDENTS_ERROR: String = "students_error"

/** The loading placeholder. */
const val TAG_STUDENTS_LOADING: String = "students_loading"

/** How many placeholder cards the loading state draws. */
private const val SKELETON_ROWS = 4

/** The add button's corner, matching the batch list's. */
private val FAB_CORNER = 16.dp

/**
 * What the Students tab can be asked to do.
 *
 * @property onOpen Called with a student id when a row is tapped
 * @property onAdd Called when the teacher wants to add a student
 * @property onFilter Called with the chosen filter
 * @property onSearch Called with the search text
 * @property onRetry Called when the teacher asks to retry
 */
data class StudentsActions(
    val onOpen: (String) -> Unit,
    val onAdd: () -> Unit,
    val onFilter: (StudentFilter) -> Unit,
    val onSearch: (String) -> Unit,
    val onRetry: () -> Unit,
)

/**
 * The teacher's students, apart from any batch [0018].
 *
 * Renders a [StudentsUiState] and decides nothing: the filter chips and
 * the search are sent to the server, which answers with the list.
 *
 * @param state What to render
 * @param filter The filter in force
 * @param query The search text in force
 * @param batches The teacher's batches, one chip each
 * @param actions What the screen can be asked to do
 * @param modifier The layout modifier
 * @param bottomBar The teacher's tab bar
 * @param barActions Icons at the bar's end
 */
@Composable
fun StudentsScreen(
    state: StudentsUiState,
    filter: StudentFilter,
    query: String,
    batches: List<BatchOption>,
    actions: StudentsActions,
    modifier: Modifier = Modifier,
    bottomBar: @Composable () -> Unit = {},
    barActions: @Composable RowScope.() -> Unit = {},
) {
    ListScreenScaffold(
        title = stringResource(R.string.students_title),
        modifier = modifier,
        bottomBar = bottomBar,
        actions = barActions,
        header = {
            OutlinedTextField(
                value = query,
                onValueChange = actions.onSearch,
                placeholder = { Text(stringResource(R.string.students_search)) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().testTag(TAG_STUDENTS_SEARCH),
            )
            FilterChips(filter = filter, batches = batches, onFilter = actions.onFilter)
        },
    ) {
        Box(Modifier.fillMaxSize()) {
            StudentsBody(state, actions)
            AddStudentFab(
                onClick = actions.onAdd,
                modifier =
                    Modifier
                        .align(Alignment.BottomEnd)
                        .padding(bottom = Spacing.screen)
                        .testTag(TAG_STUDENTS_ADD),
            )
        }
    }
}

/**
 * The list, its placeholder, its empty state or its error.
 *
 * @param state What to render
 * @param actions What the screen can be asked to do
 */
@Composable
private fun StudentsBody(state: StudentsUiState, actions: StudentsActions) {
    when (state) {
        StudentsUiState.Loading ->
            Column(Modifier.testTag(TAG_STUDENTS_LOADING), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                repeat(SKELETON_ROWS) {
                    ShikkhokCard {
                        SkeletonBlock(widthFraction = 0.55f, height = 16.dp)
                        SkeletonBlock(widthFraction = 0.35f, height = 10.dp)
                    }
                }
            }

        is StudentsUiState.Empty ->
            EmptyState(
                title =
                    stringResource(
                        if (state.filtered) R.string.students_empty_filtered else R.string.students_empty_title,
                    ),
                body = if (state.filtered) "" else stringResource(R.string.students_empty_body),
                modifier = Modifier.testTag(TAG_STUDENTS_EMPTY),
            )

        is StudentsUiState.Loaded ->
            LazyColumn(
                modifier = Modifier.testTag(TAG_STUDENTS_LIST),
                // Clears the add button, so the last row stays reachable.
                contentPadding = PaddingValues(bottom = Spacing.screen + Reach.moneyButton + Spacing.screen),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                items(state.rows, key = { it.id }) { row -> StudentRowView(row, actions.onOpen) }
            }

        is StudentsUiState.Failed ->
            EmptyState(
                title = stringResource(R.string.students_error_title),
                body = stringResource(MessageKeys.resolve(state.messageKey)),
                modifier = Modifier.testTag(TAG_STUDENTS_ERROR),
            ) {
                if (state.retryable) {
                    OutlinedButton(onClick = actions.onRetry, modifier = Modifier.heightIn(min = Reach.touch)) {
                        Text(stringResource(R.string.roster_retry))
                    }
                }
            }
    }
}

/**
 * "All", one chip per batch, then "Not in a batch".
 *
 * @param filter The filter in force
 * @param batches The teacher's batches
 * @param onFilter Called with the chosen filter
 */
@Composable
private fun FilterChips(filter: StudentFilter, batches: List<BatchOption>, onFilter: (StudentFilter) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        FilterChip(
            selected = filter == StudentFilter.All,
            onClick = { onFilter(StudentFilter.All) },
            label = { Text(stringResource(R.string.students_filter_all)) },
            modifier = Modifier.testTag(TAG_STUDENTS_FILTER),
        )
        batches.forEach { batch ->
            FilterChip(
                selected = filter == StudentFilter.InBatch(batch.id),
                onClick = { onFilter(StudentFilter.InBatch(batch.id)) },
                label = { Text(Numerals.freeText(batch.name)) },
                modifier = Modifier.testTag(TAG_STUDENTS_FILTER),
            )
        }
        FilterChip(
            selected = filter == StudentFilter.Unassigned,
            onClick = { onFilter(StudentFilter.Unassigned) },
            label = { Text(stringResource(R.string.students_filter_unassigned)) },
            modifier = Modifier.testTag(TAG_STUDENTS_FILTER),
        )
    }
}

/**
 * One student, with the batches they sit in.
 *
 * @param row The student
 * @param onOpen Called with the student id when tapped
 */
@Composable
private fun StudentRowView(row: StudentListRow, onOpen: (String) -> Unit) {
    ShikkhokCard(modifier = Modifier.testTag(TAG_STUDENT_ROW), onClick = { onOpen(row.id) }) {
        Text(
            text = Numerals.freeText(row.name),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Text(
            text =
                if (row.batchNames.isEmpty()) {
                    stringResource(R.string.students_not_in_batch)
                } else {
                    row.batchNames.joinToString(" · ") { Numerals.freeText(it) }
                },
            style = MaterialTheme.typography.labelSmall,
            color =
                if (row.batchNames.isEmpty()) {
                    MaterialTheme.colorScheme.tertiary
                } else {
                    MaterialTheme.colorScheme.onSurfaceVariant
                },
        )
    }
}

/**
 * The add-student button, in thumb reach like the batch list's.
 *
 * @param onClick Called when tapped
 * @param modifier The layout modifier
 */
@Composable
private fun AddStudentFab(onClick: () -> Unit, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        modifier = modifier.heightIn(min = Reach.moneyButton),
        shape = RoundedCornerShape(FAB_CORNER),
        contentPadding = PaddingValues(horizontal = 20.dp),
    ) {
        Icon(painter = painterResource(R.drawable.ic_add), contentDescription = null, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(Spacing.tight))
        Text(text = stringResource(R.string.students_add), style = MaterialTheme.typography.titleMedium)
    }
}
