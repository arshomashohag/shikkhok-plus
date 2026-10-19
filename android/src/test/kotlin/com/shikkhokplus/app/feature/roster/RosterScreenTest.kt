package com.shikkhokplus.app.feature.roster

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.feature.roster.ui.RosterScreen
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_EMPTY
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_ERROR
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_FETCHED_AT
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_LIST
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_LOADING
import com.shikkhokplus.app.feature.roster.ui.TAG_ROSTER_RETRY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * What the roster screen renders for a given state.
 *
 * This is the half the mapper tests cannot see: a correct state mapped
 * to a screen showing the wrong control is still a broken screen.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RosterScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun row(name: String, status: String = "roster.status.active") =
        RosterRow(
            enrollmentId = "e-$name",
            displayName = name,
            statusLabel = status,
            fee = null,
            guardianPhone = null,
        )

    @Test
    fun `loading shows a spinner`() {
        compose.setContent { RosterScreen(RosterUiState.Loading, onRetry = {}) }

        compose.onNodeWithTag(TAG_ROSTER_LOADING).assertIsDisplayed()
    }

    @Test
    fun `an empty batch explains itself rather than showing a blank list`() {
        compose.setContent {
            RosterScreen(RosterUiState.Empty("Physics"), onRetry = {})
        }

        compose.onNodeWithTag(TAG_ROSTER_EMPTY).assertIsDisplayed()
    }

    @Test
    fun `a loaded roster shows the list`() {
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded("Physics", listOf(row("Rahim")), null),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_LIST).assertIsDisplayed()
    }

    @Test
    fun `cached data says so, rather than passing as live`() {
        // The cache is a READ cache. A teacher must know when they are
        // looking at saved data; silently rendering it as current is how
        // a stale roster gets trusted in front of a class.
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded("Physics", listOf(row("Rahim")), "10:05"),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_FETCHED_AT).assertIsDisplayed()
    }

    @Test
    fun `live data shows no staleness notice`() {
        compose.setContent {
            RosterScreen(
                RosterUiState.Loaded("Physics", listOf(row("Rahim")), null),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_FETCHED_AT).assertDoesNotExist()
    }

    @Test
    fun `a retryable failure offers retry and calls back once`() {
        var retries = 0
        compose.setContent {
            RosterScreen(
                RosterUiState.Failed("error.network.unreachable", retryable = true),
                onRetry = { retries += 1 },
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_ERROR).assertIsDisplayed()
        compose.onNodeWithTag(TAG_ROSTER_RETRY).performClick()

        assertEquals(1, retries)
    }

    @Test
    fun `a non-retryable failure offers no retry`() {
        // THE RULE [TC-9]: the button appears because the SERVER said
        // retryable. A client that offered retry on every error would be
        // deciding retryability from a status code.
        compose.setContent {
            RosterScreen(
                RosterUiState.Failed("enrollment.remove.claimed", retryable = false),
                onRetry = {},
            )
        }

        compose.onNodeWithTag(TAG_ROSTER_ERROR).assertIsDisplayed()
        compose.onNodeWithTag(TAG_ROSTER_RETRY).assertDoesNotExist()
    }
}
