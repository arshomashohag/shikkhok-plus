package com.shikkhokplus.app.feature.help

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.help.ui.AskQuestionScreen
import com.shikkhokplus.app.feature.help.ui.HelpListScreen
import com.shikkhokplus.app.feature.help.ui.HelpThreadScreen
import com.shikkhokplus.app.feature.help.ui.TAG_HELP_ASK
import com.shikkhokplus.app.feature.help.ui.TAG_HELP_CLOSED
import com.shikkhokplus.app.feature.help.ui.TAG_HELP_EMPTY
import com.shikkhokplus.app.feature.help.ui.TAG_HELP_MESSAGE
import com.shikkhokplus.app.feature.help.ui.TAG_HELP_NEW_REPLY
import com.shikkhokplus.app.feature.help.ui.TAG_HELP_RETRY
import com.shikkhokplus.app.feature.help.ui.TAG_HELP_SEND
import com.shikkhokplus.app.feature.help.ui.TAG_HELP_SUBJECT
import com.shikkhokplus.app.feature.help.ui.TAG_HELP_TICKET
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The help centre's three screens, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class HelpScreensTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun ticket(id: String, status: HelpStatus, newReply: Boolean = false) =
        HelpTicket(id, "Question $id", status, "2026-11-06T05:30:00Z", newReply, "Latest line $id")

    @Test
    fun `each question says where it stands in words, with a new-reply mark`() {
        val tickets =
            listOf(
                ticket("a", HelpStatus.ANSWERED, newReply = true),
                ticket("b", HelpStatus.OPEN),
                ticket("c", HelpStatus.CLOSED),
            )
        compose.setContent {
            ShikkhokTheme {
                HelpListScreen(HelpListUiState.Loaded(tickets, 1), onBack = {}, onAsk = {}, onOpen = {}, onRetry = {})
            }
        }

        compose.onAllNodesWithTag(TAG_HELP_TICKET).assertCountEquals(3)
        compose.onNodeWithText("Answered", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("With support", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("Closed", useUnmergedTree = true).assertExists()
        compose.onAllNodesWithTag(TAG_HELP_NEW_REPLY, useUnmergedTree = true).assertCountEquals(1)
    }

    @Test
    fun `tapping a question opens it`() {
        val opened = mutableListOf<String>()
        compose.setContent {
            ShikkhokTheme {
                HelpListScreen(
                    HelpListUiState.Loaded(listOf(ticket("a", HelpStatus.OPEN)), 0),
                    onBack = {},
                    onAsk = {},
                    onOpen = { opened += it.id },
                    onRetry = {},
                )
            }
        }

        compose.onNodeWithTag(TAG_HELP_TICKET).performClick()

        assertEquals(listOf("a"), opened)
    }

    @Test
    fun `no questions offers Ask a question`() {
        var asked = 0
        compose.setContent {
            ShikkhokTheme {
                HelpListScreen(
                    HelpListUiState.Loaded(emptyList(), 0),
                    onBack = {},
                    onAsk = { asked++ },
                    onOpen = {},
                    onRetry = {},
                )
            }
        }

        compose.onNodeWithTag(TAG_HELP_EMPTY).assertExists()
        compose.onNodeWithTag(TAG_HELP_ASK).performClick()
        assertEquals(1, asked)
    }

    @Test
    fun `a failed list offers a retry when the server allows one`() {
        var retried = 0
        compose.setContent {
            ShikkhokTheme {
                HelpListScreen(
                    HelpListUiState.Failed(HelpMapper.OFFLINE_KEY, retryable = true),
                    onBack = {},
                    onAsk = {},
                    onOpen = {},
                    onRetry = { retried++ },
                )
            }
        }

        compose.onNodeWithText("Try again").performClick()
        assertEquals(1, retried)
    }

    @Test
    fun `the form reminds people to leave children's details out, and Send waits for both fields`() {
        compose.setContent {
            ShikkhokTheme {
                AskQuestionScreen(AskUiState(subject = "Hello"), onSubject = {}, onBody = {}, onSend = {}, onBack = {})
            }
        }

        compose
            .onNodeWithText("Please don't include children's personal details such as phone numbers or addresses.")
            .assertExists()
        compose.onNodeWithText("5 / 120").assertExists()
        compose.onNodeWithTag(TAG_HELP_SEND).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `typing reaches the model`() {
        val typed = mutableListOf<String>()
        compose.setContent {
            ShikkhokTheme {
                AskQuestionScreen(AskUiState(), onSubject = { typed += it }, onBody = {}, onSend = {}, onBack = {})
            }
        }

        compose.onNodeWithTag(TAG_HELP_SUBJECT).performTextInput("Cannot add")

        assertEquals(listOf("Cannot add"), typed)
    }

    @Test
    fun `a valid form can be sent`() {
        var sent = 0
        compose.setContent {
            ShikkhokTheme {
                AskQuestionScreen(
                    AskUiState(subject = "Cannot add", body = "The add button does nothing."),
                    onSubject = {},
                    onBody = {},
                    onSend = { sent++ },
                    onBack = {},
                )
            }
        }

        compose.onNodeWithTag(TAG_HELP_SEND).performScrollTo().assertIsEnabled().performClick()

        assertEquals(1, sent)
    }

    @Test
    fun `a failed send names the reason and offers an explicit retry`() {
        var sent = 0
        val state =
            AskUiState(
                subject = "Cannot add",
                body = "The add button does nothing.",
                write = WriteState.Failed(HelpMapper.OFFLINE_KEY, retryable = true),
            )
        compose.setContent {
            ShikkhokTheme { AskQuestionScreen(state, onSubject = {}, onBody = {}, onSend = { sent++ }, onBack = {}) }
        }

        compose.onNodeWithText("Could not reach the server. Check your connection and try again.").assertExists()
        compose.onNodeWithTag(TAG_HELP_RETRY).performScrollTo().performClick()
        assertEquals(1, sent)
        compose.onNodeWithText("Cannot add").assertExists()
    }

    @Test
    fun `the daily limit is explained and offers no retry`() {
        val state =
            AskUiState(
                subject = "Cannot add",
                body = "The add button does nothing.",
                write = WriteState.Failed("help.ticket.too_many", retryable = false),
            )
        compose.setContent {
            ShikkhokTheme { AskQuestionScreen(state, onSubject = {}, onBody = {}, onSend = {}, onBack = {}) }
        }

        compose
            .onNodeWithText(
                "You have reached the limit for new questions for now. " +
                    "Try again later, or add to a question you already asked.",
            ).assertExists()
        compose.onNodeWithTag(TAG_HELP_RETRY).assertDoesNotExist()
    }

    @Test
    fun `a thread signs support's messages and warns that replying reopens a closed question`() {
        val thread =
            HelpThread(
                ticket("a", HelpStatus.CLOSED),
                listOf(
                    HelpMessage("m-1", fromSupport = false, body = "The add button does nothing.", sentAt = "x"),
                    HelpMessage("m-2", fromSupport = true, body = "Try the + button.", sentAt = "x"),
                ),
                closed = true,
            )
        compose.setContent {
            ShikkhokTheme {
                HelpThreadScreen(
                    HelpThreadUiState.Loaded(thread),
                    reply = ReplyUiState(),
                    onReply = {},
                    onSend = {},
                    onRetry = {},
                    onBack = {},
                )
            }
        }

        compose.onAllNodesWithTag(TAG_HELP_MESSAGE).assertCountEquals(2)
        compose.onNodeWithText("ShikkhokPlus support", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("You", useUnmergedTree = true).assertExists()
        compose.onNodeWithTag(TAG_HELP_CLOSED).performScrollTo()
        compose.onNodeWithText("This question is closed. Replying will reopen it.").assertExists()
        compose.onNodeWithTag(TAG_HELP_SEND).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `an open thread shows no closed notice and sends a typed reply`() {
        var sent = 0
        val thread = HelpThread(ticket("a", HelpStatus.ANSWERED), emptyList(), closed = false)
        compose.setContent {
            ShikkhokTheme {
                HelpThreadScreen(
                    HelpThreadUiState.Loaded(thread),
                    reply = ReplyUiState(text = "Thanks"),
                    onReply = {},
                    onSend = { sent++ },
                    onRetry = {},
                    onBack = {},
                )
            }
        }

        compose.onNodeWithTag(TAG_HELP_CLOSED).assertDoesNotExist()
        compose.onNodeWithTag(TAG_HELP_SEND).performScrollTo().performClick()
        assertEquals(1, sent)
    }
}
