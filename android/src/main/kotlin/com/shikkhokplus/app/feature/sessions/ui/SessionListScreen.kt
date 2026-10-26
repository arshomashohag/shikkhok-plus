package com.shikkhokplus.app.feature.sessions.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.sessions.SessionRow
import com.shikkhokplus.app.feature.sessions.SessionsUiState

/** Stable test identifiers. Not user-visible text. */
const val TAG_SESSIONS_LOADING: String = "sessions_loading"

/** The batch name heading. */
const val TAG_SESSIONS_TITLE: String = "sessions_title"

/** The explanation shown when a batch has no sessions. */
const val TAG_SESSIONS_EMPTY: String = "sessions_empty"

/** The list of sessions. */
const val TAG_SESSIONS_LIST: String = "sessions_list"

/** One session. */
const val TAG_SESSION_ROW: String = "session_row"

/** The cancelled mark. Present on cancelled rows only. */
const val TAG_SESSION_CANCELLED: String = "session_cancelled"

/** The ad-hoc mark. Present on teacher-created rows only. */
const val TAG_SESSION_AD_HOC: String = "session_ad_hoc"

/** The not-yet-logged notice for a session with no topic. */
const val TAG_SESSION_TOPIC_UNLOGGED: String = "session_topic_unlogged"

/** The topic text, shown when one was written. */
const val TAG_SESSION_TOPIC: String = "session_topic"

/** The add-a-class action. */
const val TAG_SESSIONS_ADD: String = "sessions_add"

/** The error message. */
const val TAG_SESSIONS_ERROR: String = "sessions_error"

/** The retry button, shown only when the server said retryable. */
const val TAG_SESSIONS_RETRY: String = "sessions_retry"

/**
 * The teacher's classes for one batch [FR3.1, FR3.2].
 *
 * **This composable renders a [SessionsUiState] and nothing else.**
 * There is no conditional here depending on a domain value — no
 * comparison of a date against today to decide whether a class is past,
 * no `status == "cancelled"`, and no `topic != null` to decide whether
 * it was logged. Every one of those decisions was made by
 * `SessionsStateMapper` [TC-9, D-31].
 *
 * The last one is the pressure this screen puts on that rule
 * specifically: `topicLogged` and `topic` are separate fields so the
 * screen cannot collapse never-written into written-blank, which is
 * exactly what a null check here would do [BR2.2].
 *
 * @param state What to render
 * @param onOpen Called with the session the teacher tapped
 * @param onAddSession Called when the teacher wants an ad-hoc class
 * @param onRetry Called when the teacher asks to retry
 * @param modifier Layout modifier
 */
@Composable
fun SessionListScreen(
    state: SessionsUiState,
    onOpen: (SessionRow) -> Unit,
    onAddSession: () -> Unit = {},
    onRetry: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    ListScreenScaffold(
        title = stringResource(R.string.screen_title_sessions),
        modifier = modifier,
    ) {
        when (state) {
            SessionsUiState.Idle -> Unit

            SessionsUiState.Loading ->
                CircularProgressIndicator(Modifier.testTag(TAG_SESSIONS_LOADING))

            is SessionsUiState.Empty -> {
                Text(state.batchName, Modifier.testTag(TAG_SESSIONS_TITLE))
                Button(
                    onClick = onAddSession,
                    modifier = Modifier.testTag(TAG_SESSIONS_ADD),
                ) {
                    Text(stringResource(R.string.sessions_add))
                }
                // An empty list and "no classes scheduled" are
                // different states, and a blank list explains neither.
                Text(
                    stringResource(R.string.sessions_empty),
                    Modifier.testTag(TAG_SESSIONS_EMPTY),
                )
            }

            is SessionsUiState.Loaded -> {
                Text(state.batchName, Modifier.testTag(TAG_SESSIONS_TITLE))
                Button(
                    onClick = onAddSession,
                    modifier = Modifier.testTag(TAG_SESSIONS_ADD),
                ) {
                    Text(stringResource(R.string.sessions_add))
                }
                LazyColumn(Modifier.testTag(TAG_SESSIONS_LIST)) {
                    items(state.rows, key = { it.sessionId }) { row ->
                        SessionRowView(row, onOpen)
                    }
                }
            }

            is SessionsUiState.Failed -> {
                Text(
                    stringResource(MessageKeys.resolve(state.messageKey)),
                    Modifier.testTag(TAG_SESSIONS_ERROR),
                )
                if (state.retryable) {
                    Button(
                        onClick = onRetry,
                        modifier = Modifier.testTag(TAG_SESSIONS_RETRY),
                    ) {
                        Text(stringResource(R.string.sessions_retry))
                    }
                }
            }
        }
    }
}

/**
 * One class.
 *
 * @param row The session to render
 * @param onOpen Called when the teacher taps it
 */
@Composable
private fun SessionRowView(row: SessionRow, onOpen: (SessionRow) -> Unit) {
    Column(Modifier.fillMaxWidth().testTag(TAG_SESSION_ROW)) {
        TextButton(onClick = { onOpen(row) }) {
            Text(
                stringResource(
                    R.string.session_when,
                    Numerals.freeText(row.dateLabel),
                    Numerals.freeText(row.timeLabel),
                ),
            )
        }
        row.subjectName?.let { Text(Numerals.freeText(it)) }
        Text(stringResource(MessageKeys.resolve(row.statusLabel)))

        // **`isCancelled`, decided by the mapper.** Marked because a
        // cancelled class accepts no attendance [BR1.6] and a teacher
        // opening it to mark would otherwise find out at the refusal.
        if (row.isCancelled) {
            Text(
                stringResource(R.string.session_cancelled_mark),
                Modifier.testTag(TAG_SESSION_CANCELLED),
                color = MaterialTheme.colorScheme.error,
            )
        }

        // Marked because generation never touches an ad-hoc class
        // [BR1.4], so the teacher who created it is the only one who
        // will.
        if (row.isAdHoc) {
            Text(
                stringResource(R.string.session_ad_hoc_mark),
                Modifier.testTag(TAG_SESSION_AD_HOC),
            )
        }

        // **`topicLogged`, not `topic == null`** [BR2.2]. The two
        // branches below are driven by the server's own boolean, so a
        // topic deliberately saved blank renders as logged-and-blank
        // rather than as never-logged.
        if (row.topicLogged) {
            Text(
                Numerals.freeText(row.topic.orEmpty()),
                Modifier.testTag(TAG_SESSION_TOPIC),
            )
        } else {
            Text(
                stringResource(R.string.session_topic_unlogged),
                Modifier.testTag(TAG_SESSION_TOPIC_UNLOGGED),
            )
        }
    }
}
