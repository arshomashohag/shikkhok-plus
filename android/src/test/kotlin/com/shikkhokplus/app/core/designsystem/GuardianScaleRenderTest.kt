package com.shikkhokplus.app.core.designsystem

import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.unit.dp
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The guardian scale reaches the controls themselves: inside
 * [GuardianScale] the main action is drawn at the board's 60dp and a
 * secondary one at 56dp.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class GuardianScaleRenderTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `a guardian's buttons are drawn at the guardian heights`() {
        compose.setContent {
            ShikkhokTheme {
                GuardianScale(enabled = true) {
                    androidx.compose.foundation.layout.Column {
                        PrimaryButton("Pay", {}, Modifier.testTag("main"))
                        SecondaryButton("Later", {}, Modifier.testTag("other"))
                    }
                }
            }
        }

        compose.onNodeWithTag("main").assertHeightIsAtLeast(60.dp)
        compose.onNodeWithTag("other").assertHeightIsAtLeast(56.dp)
    }
}
