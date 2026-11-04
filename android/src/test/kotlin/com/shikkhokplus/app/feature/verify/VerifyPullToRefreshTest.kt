package com.shikkhokplus.app.feature.verify

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.designsystem.TAG_PULL_TO_REFRESH
import com.shikkhokplus.app.feature.verify.ui.VerifyScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * Pulling down on Verify re-reads the queue — including when it is
 * empty, which is when a teacher waiting for a bKash payment pulls.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class VerifyPullToRefreshTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun `a pull on the caught-up state asks for a refresh`() {
        var pulls = 0
        compose.setContent {
            ShikkhokTheme {
                VerifyScreen(
                    state = VerifyUiState.AllCaughtUp(recent = emptyList()),
                    onBack = {},
                    onOpen = {},
                    onRetry = {},
                    onRefresh = { pulls++ },
                )
            }
        }

        compose.onNodeWithTag(TAG_PULL_TO_REFRESH).performTouchInput { swipeDown() }
        compose.waitForIdle()

        assertEquals(1, pulls)
    }

    @Test
    fun `a screen that offers no refresh has no pull container`() {
        compose.setContent {
            ShikkhokTheme {
                VerifyScreen(
                    state = VerifyUiState.AllCaughtUp(recent = emptyList()),
                    onBack = {},
                    onOpen = {},
                    onRetry = {},
                )
            }
        }

        compose.onAllNodesWithTag(TAG_PULL_TO_REFRESH).assertCountEquals(0)
    }
}
