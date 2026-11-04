package com.shikkhokplus.app.feature.marks.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.rememberHaptics
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.marks.MarkRow
import com.shikkhokplus.app.feature.marks.MarksUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_MARK_ENTRY_LOADING: String = "mark_entry_loading"

/** The empty state, for an exam in a batch with no students. */
const val TAG_MARK_ENTRY_EMPTY: String = "mark_entry_empty"

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

/** The pencil that opens the exam's edit form. */
const val TAG_MARK_ENTRY_EDIT_EXAM: String = "mark_entry_edit_exam"

/** The link to one seat's mark history. */
const val TAG_MARK_ENTRY_HISTORY: String = "mark_entry_history"

/** The "6/20" counter in the bar. */
const val TAG_MARK_ENTRY_COUNTER: String = "mark_entry_counter"

/** The "now entering" dock above the keypad. */
const val TAG_MARK_ENTRY_DOCK: String = "mark_entry_dock"

/** One keypad key; the digit or action follows the underscore. */
const val TAG_MARK_ENTRY_KEY: String = "mark_entry_key"

/** The keypad's Next key. */
const val TAG_MARK_ENTRY_NEXT: String = "mark_entry_next"

/** The dock's delete-one-digit control. */
const val TAG_MARK_ENTRY_BACKSPACE: String = "mark_entry_backspace"

/**
 * Mark entry for one exam [FR4.2, FR4.3], as continuous entry (T3).
 *
 * **One student at a time, on the app's own keypad.** The list shows
 * every seat compactly -- roll number, name, mark, "/25" -- and the dock
 * under it names the student being entered. Digits go into that
 * student's box; **Next** saves it and moves down. A teacher marking a
 * stack of papers types, taps Next, types, and never waits for the
 * system keyboard to open, close or cover the next row.
 *
 * **This composable renders a [MarksUiState] and nothing else.** Which
 * label a result state carries, whether a seat may be marked at all
 * (`joined_after` cannot [BR4.3]), and whether the exam accepts writes
 * [BR5.5] are all the mapper's decisions.
 *
 * **The keypad is format-only, never policy.** It types digits; whether
 * a number is within the exam's total is the **server's** check [BR4.2],
 * because a client bound would diverge the moment an exam is edited.
 * Marks are whole numbers because the API's mark is an integer, so the
 * board's decimal key is not drawn.
 *
 * **An empty box is not a zero.** A zero is a mark the student earned;
 * an empty box is a mark nobody has entered [BR4.2], and **Absent** is
 * its own action, a fact the teacher recorded [BR4.3].
 *
 * @param state What to render
 * @param onMark Called with the seat and the score the teacher entered
 * @param onAbsent Called with the seat the teacher marked absent
 * @param onRetry Called when the teacher asks to retry
 * @param modifier Layout modifier
 * @param onEditExam Called by the pencil, to edit the exam
 * @param onHistory Called to see every mark recorded for a seat
 */
@Composable
fun MarkEntryScreen(
    state: MarksUiState,
    onMark: (MarkRow, Int) -> Unit = { _, _ -> },
    onAbsent: (MarkRow) -> Unit = {},
    onRetry: () -> Unit = {},
    modifier: Modifier = Modifier,
    onEditExam: () -> Unit = {},
    onHistory: (MarkRow) -> Unit = {},
) {
    val loaded = state as? MarksUiState.EntryLoaded
    val entry = rememberEntry(loaded, onMark)
    // **The exam is the title** (T3), with what it is out of under it.
    ListScreenScaffold(
        title = loaded?.let { Numerals.freeText(it.examTitle) } ?: stringResource(R.string.screen_title_mark_entry),
        subtitle = loaded?.let { stringResource(R.string.batch_exam_out_of, Numerals.count(it.totalMarks)) },
        modifier = modifier,
        actions = { BarActions(loaded, onEditExam) },
        header = { loaded?.let { Progress(it.rows) } },
        bottomBar = {
            val current = entry.current
            if (loaded != null && loaded.writable && current != null) {
                Dock(entry, current, loaded.rows.indexOf(current), onAbsent, onHistory)
            }
        },
    ) {
        when (state) {
            MarksUiState.Loading -> SkeletonList(rows = 6, modifier = Modifier.testTag(TAG_MARK_ENTRY_LOADING))

            is MarksUiState.EntryLoaded -> {
                if (!state.writable) {
                    Text(
                        stringResource(R.string.mark_entry_read_only),
                        Modifier.testTag(TAG_MARK_ENTRY_READ_ONLY),
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                if (state.rows.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.mark_entry_empty_title),
                        body = stringResource(R.string.mark_entry_empty_body),
                        modifier = Modifier.testTag(TAG_MARK_ENTRY_EMPTY),
                    )
                }
                LazyColumn(
                    Modifier
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
                        .testTag(TAG_MARK_ENTRY_LIST),
                ) {
                    itemsIndexed(state.rows, key = { _, row -> row.enrollmentId }) { index, row ->
                        if (index > 0) HorizontalDivider(color = MaterialTheme.colorScheme.surfaceContainerHigh)
                        MarkLine(
                            row = row,
                            roll = index + 1,
                            totalMarks = state.totalMarks,
                            current = row.enrollmentId == entry.current?.enrollmentId,
                            typed = entry.typed,
                            onSelect = if (state.writable && row.isEditable) ({ entry.select(row) }) else null,
                        )
                    }
                }
            }

            is MarksUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_MARK_ENTRY_ERROR),
                )
                if (state.retryable) {
                    Button(onClick = onRetry, modifier = Modifier.testTag(TAG_MARK_ENTRY_RETRY)) {
                        Text(stringResource(R.string.mark_entry_retry))
                    }
                }
            }

            else -> Unit
        }
    }
}

/**
 * Who is being entered and what has been typed for them.
 *
 * **The first seat without a mark is where entry starts**, so opening a
 * half-marked exam lands on the next paper rather than the first one.
 *
 * @property current The seat being entered, or null when none can be
 * @property typed The digits typed for it so far
 * @property select Saves the open seat, then opens another
 * @property type Adds a digit
 * @property backspace Removes the last digit
 * @property next Saves the open seat and moves to the next one
 */
private class Entry(
    val current: MarkRow?,
    val typed: String,
    val select: (MarkRow) -> Unit,
    val type: (Char) -> Unit,
    val backspace: () -> Unit,
    val next: () -> Unit,
)

/**
 * Hold the open seat and its typed digits across recompositions.
 *
 * **Saved once, when the teacher moves on** -- Next, or tapping another
 * row -- and only when the digits differ from what is stored: saving
 * every key sent "2" before "22".
 *
 * @param loaded The exam, or null while it loads
 * @param onMark Called to save a seat's mark
 * @return The entry
 */
@Composable
private fun rememberEntry(loaded: MarksUiState.EntryLoaded?, onMark: (MarkRow, Int) -> Unit): Entry {
    val rows = loaded?.rows.orEmpty()
    val editable = if (loaded?.writable == true) rows.filter { it.isEditable } else emptyList()
    var openId by remember(loaded?.examId) { mutableStateOf<String?>(null) }
    val current =
        editable.firstOrNull { it.enrollmentId == openId }
            ?: editable.firstOrNull { it.stateLabel == NOT_ENTERED_KEY }
            ?: editable.firstOrNull()
    var typed by remember(current?.enrollmentId, current?.marks) {
        mutableStateOf(current?.marks?.toString().orEmpty())
    }
    val haptics = rememberHaptics()
    val save = {
        val seat = current
        if (seat != null) typed.toIntOrNull()?.takeIf { it != seat.marks }?.let { onMark(seat, it) }
    }
    return Entry(
        current = current,
        typed = typed,
        select = { row ->
            if (row.enrollmentId != current?.enrollmentId) {
                save()
                openId = row.enrollmentId
            }
        },
        type = { digit -> if (typed.length < MAX_DIGITS) typed += digit },
        backspace = { typed = typed.dropLast(1) },
        next = {
            save()
            haptics.tick()
            val at = editable.indexOfFirst { it.enrollmentId == current?.enrollmentId }
            editable.getOrNull(at + 1)?.let { openId = it.enrollmentId }
        },
    )
}

/**
 * The pencil, and the "6/20" count of seats with a mark or an absence.
 *
 * @param loaded The exam, or null while it loads
 * @param onEditExam Called by the pencil
 */
@Composable
private fun BarActions(loaded: MarksUiState.EntryLoaded?, onEditExam: () -> Unit) {
    if (loaded == null) return
    val (done, of) = progressOf(loaded.rows)
    if (of > 0) {
        Text(
            stringResource(R.string.mark_entry_counter, Numerals.count(done), Numerals.count(of)),
            style = MaterialTheme.typography.titleSmall,
            modifier = Modifier.padding(end = Spacing.tight).testTag(TAG_MARK_ENTRY_COUNTER),
        )
    }
    if (loaded.writable) {
        IconButton(onClick = onEditExam, modifier = Modifier.testTag(TAG_MARK_ENTRY_EDIT_EXAM)) {
            Icon(painterResource(R.drawable.ic_edit), stringResource(R.string.exam_edit_title), Modifier.size(22.dp))
        }
    }
}

/**
 * The thin bar under the title, as far along as the counter says.
 *
 * @param rows The seats
 */
@Composable
private fun Progress(rows: List<MarkRow>) {
    val (done, of) = progressOf(rows)
    if (of == 0) return
    Box(
        Modifier
            .fillMaxWidth()
            .height(4.dp)
            .background(MaterialTheme.colorScheme.surfaceContainerHigh),
    ) {
        Box(
            Modifier
                .fillMaxWidth(done.toFloat() / of)
                .fillMaxHeight()
                .background(MaterialTheme.colorScheme.primary),
        )
    }
}

/**
 * How many seats that can be marked have a mark or an absence, of how
 * many can be marked. Read from the mapper's state labels; nothing here
 * decides what counts as marked.
 *
 * @param rows The seats
 * @return Done, then the total
 */
private fun progressOf(rows: List<MarkRow>): Pair<Int, Int> {
    val markable = rows.filter { it.isEditable }
    return markable.count { it.stateLabel != NOT_ENTERED_KEY } to markable.size
}

/**
 * One seat: roll number, name, its mark (or Absent, or an empty box),
 * and "/25".
 *
 * @param row The seat
 * @param roll Its position in the list, from 1
 * @param totalMarks What the exam is out of
 * @param current Whether this is the seat being entered
 * @param typed The digits typed for the open seat
 * @param onSelect Opens this seat, or null when it cannot be marked
 */
@Composable
private fun MarkLine(
    row: MarkRow,
    roll: Int,
    totalMarks: Int,
    current: Boolean,
    typed: String,
    onSelect: (() -> Unit)?,
) {
    val colors = MaterialTheme.colorScheme
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = Reach.rowMarksEntry)
            .then(if (onSelect != null) Modifier.clickable(role = Role.Button, onClick = onSelect) else Modifier)
            .padding(horizontal = Spacing.screen)
            .testTag(TAG_MARK_ENTRY_ROW),
        horizontalArrangement = Arrangement.spacedBy(Spacing.listItem),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            rollLabel(roll),
            style = MaterialTheme.typography.bodySmall,
            color = colors.onSurfaceVariant,
            modifier = Modifier.width(24.dp),
        )
        Text(
            Numerals.freeText(row.displayName),
            style = MaterialTheme.typography.bodyMedium,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        when {
            !row.isEditable ->
                Text(
                    stringResource(R.string.mark_entry_locked),
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.onSurfaceVariant,
                    modifier = Modifier.weight(1f).testTag(TAG_MARK_ENTRY_LOCKED),
                )
            current -> MarkBox(typed, active = true)
            row.stateLabel == ABSENT_KEY ->
                Text(
                    stringResource(MessageKeys.resolve(row.stateLabel)),
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold),
                    color = colors.onSurfaceVariant,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.width(64.dp).testTag(TAG_MARK_ENTRY_STATE),
                )
            row.marks != null ->
                Text(
                    Numerals.count(row.marks),
                    style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold),
                    textAlign = TextAlign.Center,
                    modifier = Modifier.width(64.dp).testTag(TAG_MARK_ENTRY_STATE),
                )
            else -> MarkBox("", active = false)
        }
        if (row.isEditable) {
            Text(
                stringResource(R.string.mark_entry_out_of, Numerals.count(totalMarks)),
                style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Normal),
                color = colors.onSurfaceVariant,
                modifier = Modifier.width(36.dp),
            )
        }
    }
}

/**
 * The mark's box: outlined in the primary colour while it is the seat
 * being entered.
 *
 * @param text What it holds
 * @param active Whether it is the open seat's box
 */
@Composable
private fun MarkBox(text: String, active: Boolean) {
    val colors = MaterialTheme.colorScheme
    Box(
        Modifier
            .width(64.dp)
            .height(Reach.touch)
            .background(colors.surface, MaterialTheme.shapes.small)
            .border(
                if (active) 2.dp else 1.5.dp,
                if (active) colors.primary else colors.surfaceContainerHigh,
                MaterialTheme.shapes.small,
            )
            .then(if (active) Modifier.testTag(TAG_MARK_ENTRY_FIELD) else Modifier),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold))
    }
}

/**
 * "07 · now entering", the student's name, Absent, history and
 * backspace, then the keypad.
 *
 * @param entry The open seat and its digits
 * @param current The seat being entered
 * @param index Its position in the list
 * @param onAbsent Called to mark it absent
 * @param onHistory Called to see its marks
 */
@Composable
private fun Dock(
    entry: Entry,
    current: MarkRow,
    index: Int,
    onAbsent: (MarkRow) -> Unit,
    onHistory: (MarkRow) -> Unit,
) {
    val haptics = rememberHaptics()
    val colors = MaterialTheme.colorScheme
    Column(Modifier.fillMaxWidth().background(colors.surface).testTag(TAG_MARK_ENTRY_DOCK)) {
        HorizontalDivider(color = colors.surfaceContainerHigh)
        Row(
            Modifier
                .fillMaxWidth()
                .heightIn(min = Reach.rowSingle)
                .padding(start = Spacing.screen, end = Spacing.tight),
            horizontalArrangement = Arrangement.spacedBy(Spacing.tight),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(
                    stringResource(R.string.mark_entry_now_entering, rollLabel(index + 1)),
                    style = MaterialTheme.typography.bodySmall,
                    color = colors.onSurfaceVariant,
                )
                Text(
                    Numerals.freeText(current.displayName),
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (current.hasHistory) {
                TextAction(
                    stringResource(R.string.mark_history_open),
                    { onHistory(current) },
                    Modifier.testTag(TAG_MARK_ENTRY_HISTORY),
                )
            }
            // **Absent is its own action, not an empty box** [BR4.3].
            TextAction(
                stringResource(R.string.mark_entry_absent),
                {
                    haptics.tick()
                    onAbsent(current)
                },
                Modifier.testTag(TAG_MARK_ENTRY_ABSENT),
            )
            IconButton(onClick = entry.backspace, modifier = Modifier.testTag(TAG_MARK_ENTRY_BACKSPACE)) {
                val label = stringResource(R.string.mark_entry_backspace)
                Text(
                    "⌫",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.semantics { contentDescription = label },
                )
            }
        }
        Keypad(entry)
    }
}

/**
 * Three columns of keys: 1 to 9, then a blank, 0 and Next.
 *
 * @param entry Where the keys type
 */
@Composable
private fun Keypad(entry: Entry) {
    val colors = MaterialTheme.colorScheme
    Column(
        Modifier.fillMaxWidth().background(colors.surfaceContainerHigh).padding(Spacing.tight),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        KEY_ROWS.forEach { keys ->
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                keys.forEach { key ->
                    when (key) {
                        ' ' -> Box(Modifier.weight(1f))
                        NEXT -> Key(stringResource(R.string.mark_entry_next), TAG_MARK_ENTRY_NEXT, entry.next)
                        else -> Key(key.toString(), TAG_MARK_ENTRY_KEY + "_" + key) { entry.type(key) }
                    }
                }
            }
        }
    }
}

/**
 * One key: a white 48dp tile.
 *
 * @param label What it shows
 * @param tag Its test tag
 * @param onPress Called when pressed
 */
@Composable
private fun RowScope.Key(label: String, tag: String, onPress: () -> Unit) {
    Box(
        Modifier
            .weight(1f)
            .height(Reach.touch)
            .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.small)
            .clickable(role = Role.Button, onClick = onPress)
            .testTag(tag),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, style = MaterialTheme.typography.titleLarge)
    }
}

/**
 * A roll number as the board prints it, "07", in Latin digits as every
 * count in the app is [NFR3.3].
 *
 * @param roll The position, from 1
 * @return It, two digits wide
 */
private fun rollLabel(roll: Int): String = Numerals.count(roll).padStart(2, '0')

/** The mapper's key for a seat nobody has marked yet. */
private const val NOT_ENTERED_KEY = "mark.state.not_entered"

/** The mapper's key for a seat marked absent. */
private const val ABSENT_KEY = "mark.state.absent"

/** The keypad's Next key, in [KEY_ROWS]. */
private const val NEXT = '>'

/** The keypad's layout; a space is an empty cell. */
private val KEY_ROWS = listOf("123", "456", "789", " 0$NEXT").map { it.toList() }

/** Enough digits for any exam total; the range is the server's check. */
private const val MAX_DIGITS = 3
