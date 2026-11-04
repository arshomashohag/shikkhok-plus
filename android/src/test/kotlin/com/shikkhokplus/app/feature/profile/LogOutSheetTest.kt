package com.shikkhokplus.app.feature.profile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.feature.profile.ui.LogOutSheetContent
import com.shikkhokplus.app.feature.profile.ui.TAG_LOG_OUT_CONFIRM
import com.shikkhokplus.app.feature.profile.ui.TAG_LOG_OUT_STAY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The log-out sheet (T9 "Log out · unsent work warning").
 *
 * **Never silent about unsent work**: with records waiting, the sheet
 * names how many, says they would be deleted, and makes staying the
 * first choice. With nothing waiting, it is a plain confirmation.
 *
 * The content is rendered without its modal sheet, as the other sheet
 * tests here do: Robolectric does not lay a modal window out reliably
 * enough to tap inside it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class LogOutSheetTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `unsent records are counted and staying is the first choice`() {
        var stays = 0
        var logOuts = 0
        compose.setContent { LogOutSheetContent(unsent = 2, onConfirm = { logOuts++ }, onDismiss = { stays++ }) }

        compose.onNodeWithText("Log out of ShikkhokPlus?").assertIsDisplayed()
        compose.onNodeWithText("2 records haven't been sent yet.").assertIsDisplayed()
        compose.onNodeWithText("Stay and send them first").assertIsDisplayed()

        compose.onNodeWithTag(TAG_LOG_OUT_STAY).performClick()
        assertEquals(1, stays)
        assertEquals(0, logOuts, "staying must not log out")
    }

    @Test
    fun `log out anyway logs out`() {
        var logOuts = 0
        compose.setContent { LogOutSheetContent(unsent = 2, onConfirm = { logOuts++ }, onDismiss = {}) }

        compose.onNodeWithText("Log out anyway").assertIsDisplayed()
        compose.onNodeWithTag(TAG_LOG_OUT_CONFIRM).performClick()

        assertEquals(1, logOuts)
    }

    @Test
    fun `with nothing unsent there is no warning`() {
        var logOuts = 0
        compose.setContent { LogOutSheetContent(unsent = 0, onConfirm = { logOuts++ }, onDismiss = {}) }

        compose.onNodeWithText("haven't been sent", substring = true).assertDoesNotExist()
        compose.onNodeWithTag(TAG_LOG_OUT_CONFIRM).performClick()

        assertEquals(1, logOuts)
    }
}
