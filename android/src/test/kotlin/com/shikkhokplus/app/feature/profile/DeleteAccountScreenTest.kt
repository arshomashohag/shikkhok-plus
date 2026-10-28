package com.shikkhokplus.app.feature.profile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.feature.profile.ui.DeleteAccountScreen
import com.shikkhokplus.app.feature.profile.ui.TAG_DELETE_CLOSE
import com.shikkhokplus.app.feature.profile.ui.TAG_DELETE_CONFIRM
import com.shikkhokplus.app.feature.profile.ui.TAG_DELETE_DONE
import com.shikkhokplus.app.feature.profile.ui.TAG_DELETE_ERROR
import com.shikkhokplus.app.feature.profile.ui.TAG_DELETE_KEEP
import com.shikkhokplus.app.feature.profile.ui.TAG_DELETE_NUMBER
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The in-app deletion path (O5) [TC-19] -- the second of the two
 * deletion routes `project.md` makes release-blocking.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class DeleteAccountScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val confirming = DeletionState.Confirming("+8801611477203")

    @Test
    fun `delete stays disabled until the number matches`() {
        compose.setContent {
            DeleteAccountScreen(confirming, onDelete = {}, onKeep = {}, onDone = {})
        }
        compose.onNodeWithTag(TAG_DELETE_CONFIRM).performScrollTo().assertIsNotEnabled()

        compose.onNodeWithTag(TAG_DELETE_NUMBER).performTextInput("01611-477203")

        compose.onNodeWithTag(TAG_DELETE_CONFIRM).performScrollTo().assertIsEnabled()
    }

    @Test
    fun `delete sends what was typed, once tapped`() {
        var sent: String? = null
        compose.setContent {
            DeleteAccountScreen(confirming, onDelete = { sent = it }, onKeep = {}, onDone = {})
        }
        compose.onNodeWithTag(TAG_DELETE_NUMBER).performTextInput("01611477203")
        assertEquals(null, sent, "typing must not delete")

        compose.onNodeWithTag(TAG_DELETE_CONFIRM).performScrollTo().performClick()

        assertEquals("01611477203", sent)
    }

    @Test
    fun `keep my account backs out`() {
        var kept = 0
        compose.setContent {
            DeleteAccountScreen(confirming, onDelete = {}, onKeep = { kept++ }, onDone = {})
        }

        compose.onNodeWithTag(TAG_DELETE_KEEP).performScrollTo().performClick()

        assertEquals(1, kept)
    }

    @Test
    fun `a refusal is shown beside the form`() {
        compose.setContent {
            DeleteAccountScreen(
                DeletionState.Failed("+8801611477203", "error.network.unreachable", true),
                onDelete = {},
                onKeep = {},
                onDone = {},
            )
        }

        compose.onNodeWithTag(TAG_DELETE_ERROR).performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_DELETE_NUMBER).assertIsDisplayed()
    }

    @Test
    fun `the done screen ends the session when closed`() {
        var done = 0
        compose.setContent {
            DeleteAccountScreen(DeletionState.Deleted, onDelete = {}, onKeep = {}, onDone = { done++ })
        }
        compose.onNodeWithTag(TAG_DELETE_DONE).assertIsDisplayed()
        compose.onNodeWithTag(TAG_DELETE_NUMBER).assertDoesNotExist()

        compose.onNodeWithTag(TAG_DELETE_CLOSE).performScrollTo().performClick()

        assertEquals(1, done)
    }
}
