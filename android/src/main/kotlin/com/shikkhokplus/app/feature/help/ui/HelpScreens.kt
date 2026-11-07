package com.shikkhokplus.app.feature.help.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.StateFade
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dateTimeLabel
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.core.ui.ago
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.help.AskUiState
import com.shikkhokplus.app.feature.help.HELP_BODY_MAX
import com.shikkhokplus.app.feature.help.HELP_SUBJECT_MAX
import com.shikkhokplus.app.feature.help.HelpListUiState
import com.shikkhokplus.app.feature.help.HelpMessage
import com.shikkhokplus.app.feature.help.HelpStatus
import com.shikkhokplus.app.feature.help.HelpThread
import com.shikkhokplus.app.feature.help.HelpThreadUiState
import com.shikkhokplus.app.feature.help.HelpTicket
import com.shikkhokplus.app.feature.help.ReplyUiState

/** One question in the list. */
const val TAG_HELP_TICKET: String = "help_ticket"

/** The empty list. */
const val TAG_HELP_EMPTY: String = "help_empty"

/** The Ask a question button, on the list. */
const val TAG_HELP_ASK: String = "help_ask"

/** The new-reply mark on a question. */
const val TAG_HELP_NEW_REPLY: String = "help_new_reply"

/** The subject field. */
const val TAG_HELP_SUBJECT: String = "help_subject"

/** The question field. */
const val TAG_HELP_BODY: String = "help_body"

/** The Send button, on the form and under a thread. */
const val TAG_HELP_SEND: String = "help_send"

/** The retry after a failed send. */
const val TAG_HELP_RETRY: String = "help_retry"

/** One message in a thread. */
const val TAG_HELP_MESSAGE: String = "help_message"

/** The reply field. */
const val TAG_HELP_REPLY: String = "help_reply"

/** The closed-question notice above the reply box. */
const val TAG_HELP_CLOSED: String = "help_closed"

/**
 * My questions: the reader's own questions to support, most recently
 * active first, each with where it stands.
 *
 * @param state What to render
 * @param onBack Called to leave
 * @param onAsk Called to open Ask a question
 * @param onOpen Called with the question tapped
 * @param onRetry Called to read again after a failure
 * @param modifier The layout modifier
 * @param refreshing Whether a pull-to-refresh is in flight
 * @param onRefresh What pulling down does, or null for no pull
 */
@Composable
fun HelpListScreen(
    state: HelpListUiState,
    onBack: () -> Unit,
    onAsk: () -> Unit,
    onOpen: (HelpTicket) -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
    refreshing: Boolean = false,
    onRefresh: (() -> Unit)? = null,
) {
    ListScreenScaffold(
        title = stringResource(R.string.help_title),
        subtitle = stringResource(R.string.help_my_questions),
        modifier = modifier,
        onBack = onBack,
        refreshing = refreshing,
        onRefresh = onRefresh,
    ) {
        StateFade(state, spacing = Spacing.tight, modifier = Modifier.fillMaxSize()) { shown ->
            when (shown) {
                HelpListUiState.Loading -> SkeletonList(modifier = Modifier.padding(top = 8.dp))
                is HelpListUiState.Failed ->
                    ErrorCard(
                        title = stringResource(MessageKeys.resolve(shown.messageKey)),
                        body = null,
                        modifier = Modifier.padding(top = 8.dp),
                        retryLabel = if (shown.retryable) stringResource(R.string.auth_retry) else null,
                        onRetry = if (shown.retryable) onRetry else null,
                    )
                is HelpListUiState.Loaded ->
                    if (shown.tickets.isEmpty()) {
                        // Scrollable so a pull works on an empty list too.
                        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
                            EmptyState(
                                title = stringResource(R.string.help_empty_title),
                                body = stringResource(R.string.help_empty_body),
                                modifier = Modifier.padding(top = 8.dp).testTag(TAG_HELP_EMPTY),
                                action = { AskButton(onAsk) },
                            )
                        }
                    } else {
                        Tickets(shown.tickets, onAsk, onOpen)
                    }
            }
        }
    }
}

/**
 * The Ask a question button.
 *
 * @param onAsk Called when tapped
 */
@Composable
private fun AskButton(onAsk: () -> Unit) {
    PrimaryButton(
        text = stringResource(R.string.help_ask),
        onClick = onAsk,
        modifier = Modifier.fillMaxWidth().testTag(TAG_HELP_ASK),
    )
}

/**
 * The questions, under the Ask button.
 *
 * @param tickets In the server's order
 * @param onAsk Called to ask another
 * @param onOpen Called with the question tapped
 */
@Composable
private fun Tickets(tickets: List<HelpTicket>, onAsk: () -> Unit, onOpen: (HelpTicket) -> Unit) {
    LazyColumn(
        Modifier.fillMaxSize().padding(top = 8.dp),
        verticalArrangement = Arrangement.spacedBy(Spacing.tight),
    ) {
        item { AskButton(onAsk) }
        items(tickets, key = { it.id }) { ticket -> TicketRow(ticket, onOpen) }
    }
}

/**
 * One question: its subject, where it stands, the latest line and when.
 *
 * @param ticket The question
 * @param onOpen Called when tapped
 */
@Composable
private fun TicketRow(ticket: HelpTicket, onOpen: (HelpTicket) -> Unit) {
    ShikkhokCard(onClick = { onOpen(ticket) }, modifier = Modifier.testTag(TAG_HELP_TICKET)) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(Spacing.tight),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                Numerals.freeText(ticket.subject),
                style =
                    MaterialTheme.typography.bodyLarge.copy(
                        fontWeight = if (ticket.newReply) FontWeight.Bold else FontWeight.SemiBold,
                    ),
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            Text(
                ago(ticket.updatedAt),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        StatusLine(ticket.status, ticket.newReply)
        if (ticket.preview.isNotBlank()) {
            Text(
                Numerals.freeText(ticket.preview),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

/**
 * Where a question stands, in words, with a dot and "New reply" when
 * support has answered since the reader last looked.
 *
 * @param status Where it stands
 * @param newReply Whether the server marked an unseen reply
 */
@Composable
private fun StatusLine(status: HelpStatus, newReply: Boolean) {
    val colors = MaterialTheme.colorScheme
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(
            stringResource(statusLabel(status)),
            style = MaterialTheme.typography.labelLarge,
            color = if (status == HelpStatus.ANSWERED) colors.primary else colors.onSurfaceVariant,
        )
        if (newReply) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.testTag(TAG_HELP_NEW_REPLY),
            ) {
                Box(Modifier.size(8.dp).background(colors.primary, CircleShape))
                Text(
                    stringResource(R.string.help_new_reply),
                    style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold),
                    color = colors.primary,
                )
            }
        }
    }
}

/**
 * A status's words.
 *
 * @param status Where a question stands
 * @return Its string resource
 */
internal fun statusLabel(status: HelpStatus): Int =
    when (status) {
        HelpStatus.OPEN -> R.string.help_status_open
        HelpStatus.ANSWERED -> R.string.help_status_answered
        HelpStatus.CLOSED -> R.string.help_status_closed
    }

/**
 * Ask a question: a subject, the question, a reminder to leave
 * children's details out, and Send.
 *
 * Send stays disabled until both fields hold something; the counters
 * show how much room is left. A failed send keeps both fields and
 * offers an explicit retry when the server says one can help.
 *
 * @param state What to render
 * @param onSubject Called with the subject as typed
 * @param onBody Called with the question as typed
 * @param onSend Called to send, and to retry a failed send
 * @param onBack Called to leave
 * @param modifier The layout modifier
 */
@Composable
fun AskQuestionScreen(
    state: AskUiState,
    onSubject: (String) -> Unit,
    onBody: (String) -> Unit,
    onSend: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val saving = state.write == WriteState.Saving
    ScreenScaffold(title = stringResource(R.string.help_ask), modifier = modifier, onBack = onBack) {
        Banner(title = stringResource(R.string.help_privacy_hint), tone = BannerTone.NEUTRAL)
        ShikkhokTextField(
            value = state.subject,
            onValueChange = onSubject,
            label = stringResource(R.string.help_subject_label),
            placeholder = stringResource(R.string.help_subject_placeholder),
            help = counter(state.subject.length, HELP_SUBJECT_MAX),
            enabled = !saving,
            fieldModifier = Modifier.testTag(TAG_HELP_SUBJECT),
        )
        ShikkhokTextField(
            value = state.body,
            onValueChange = onBody,
            label = stringResource(R.string.help_body_label),
            help = counter(state.body.length, HELP_BODY_MAX),
            enabled = !saving,
            singleLine = false,
            minLines = 5,
            fieldModifier = Modifier.testTag(TAG_HELP_BODY),
        )
        WriteFailure(state.write, onSend)
        PrimaryButton(
            text = stringResource(if (saving) R.string.help_sending else R.string.help_send),
            onClick = onSend,
            enabled = state.canSend,
            modifier = Modifier.fillMaxWidth().testTag(TAG_HELP_SEND),
        )
    }
}

/**
 * "12 / 120": how much of a field's room is used.
 *
 * @param used Characters typed
 * @param max The most allowed
 * @return The counter text
 */
@Composable
private fun counter(used: Int, max: Int): String =
    stringResource(R.string.help_char_count, Numerals.count(used), Numerals.count(max))

/**
 * A failed send: the server's reason, and a retry when it can help.
 * Draws nothing for any other write state.
 *
 * @param write Where the send stands
 * @param onRetry Called to send again
 */
@Composable
private fun WriteFailure(write: WriteState, onRetry: () -> Unit) {
    val failed = write as? WriteState.Failed ?: return
    Banner(title = stringResource(MessageKeys.resolve(failed.messageKey)), tone = BannerTone.ERROR)
    if (failed.retryable) {
        SecondaryButton(
            text = stringResource(R.string.auth_retry),
            onClick = onRetry,
            modifier = Modifier.fillMaxWidth().testTag(TAG_HELP_RETRY),
        )
    }
}

/**
 * One question's thread, oldest message first, with a reply box under it.
 *
 * @param state What to render
 * @param reply The reply box
 * @param onReply Called with the reply as typed
 * @param onSend Called to send the reply, and to retry a failed send
 * @param onRetry Called to read the thread again after a failure
 * @param onBack Called to leave
 * @param modifier The layout modifier
 */
@Composable
fun HelpThreadScreen(
    state: HelpThreadUiState,
    reply: ReplyUiState,
    onReply: (String) -> Unit,
    onSend: () -> Unit,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val subject = (state as? HelpThreadUiState.Loaded)?.thread?.ticket?.subject
    ScreenScaffold(
        title = stringResource(R.string.help_thread_title),
        subtitle = subject?.let(Numerals::freeText),
        modifier = modifier,
        onBack = onBack,
    ) {
        when (state) {
            HelpThreadUiState.Loading -> SkeletonList(rows = 3)
            is HelpThreadUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) onRetry else null,
                )
            is HelpThreadUiState.Loaded -> Thread(state.thread, reply, onReply, onSend)
        }
    }
}

/**
 * The messages and the reply box.
 *
 * @param thread The question and its messages
 * @param reply The reply box
 * @param onReply Called with the reply as typed
 * @param onSend Called to send or retry
 */
@Composable
private fun Thread(thread: HelpThread, reply: ReplyUiState, onReply: (String) -> Unit, onSend: () -> Unit) {
    thread.messages.forEach { Bubble(it) }
    if (thread.closed) {
        Banner(
            title = stringResource(R.string.help_closed_notice),
            tone = BannerTone.NEUTRAL,
            modifier = Modifier.testTag(TAG_HELP_CLOSED),
        )
    }
    val saving = reply.write == WriteState.Saving
    ShikkhokTextField(
        value = reply.text,
        onValueChange = onReply,
        label = stringResource(R.string.help_reply_label),
        help = counter(reply.text.length, HELP_BODY_MAX),
        enabled = !saving,
        singleLine = false,
        minLines = 3,
        fieldModifier = Modifier.testTag(TAG_HELP_REPLY),
    )
    WriteFailure(reply.write, onSend)
    PrimaryButton(
        text = stringResource(if (saving) R.string.help_sending else R.string.help_send),
        onClick = onSend,
        enabled = reply.canSend,
        modifier = Modifier.fillMaxWidth().testTag(TAG_HELP_SEND),
    )
}

/**
 * One message as a bubble: the reader's on the right on the primary
 * wash, support's on the left on the surface, signed "ShikkhokPlus
 * support".
 *
 * @param message The message
 */
@Composable
private fun Bubble(message: HelpMessage) {
    val colors = MaterialTheme.colorScheme
    val mine = !message.fromSupport
    Box(
        Modifier.fillMaxWidth().testTag(TAG_HELP_MESSAGE),
        contentAlignment = if (mine) Alignment.CenterEnd else Alignment.CenterStart,
    ) {
        Column(
            Modifier
                .widthIn(max = 320.dp)
                .background(if (mine) colors.primaryContainer else colors.surface, MaterialTheme.shapes.medium)
                .heightIn(min = 48.dp)
                .padding(horizontal = Spacing.listItem, vertical = Spacing.tight),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Text(
                stringResource(if (mine) R.string.help_from_you else R.string.help_from_support),
                style = MaterialTheme.typography.labelLarge,
                color = if (mine) colors.onPrimaryContainer else colors.primary,
            )
            Text(
                Numerals.freeText(message.body),
                style = MaterialTheme.typography.bodyMedium,
                color = if (mine) colors.onPrimaryContainer else colors.onSurface,
            )
            Text(
                dateTimeLabel(message.sentAt),
                style = MaterialTheme.typography.bodySmall,
                color = colors.onSurfaceVariant,
            )
        }
    }
}
