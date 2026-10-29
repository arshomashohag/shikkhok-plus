package com.shikkhokplus.app.feature.guardian

import androidx.activity.ComponentActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.feature.guardian.ui.GuardianActions
import com.shikkhokplus.app.feature.guardian.ui.GuardianHomeScreen
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_CHIP
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_EMPTY
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_PAY
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_SELECTED_NAME
import com.shikkhokplus.app.feature.guardian.ui.TAG_GUARDIAN_SWITCHER
import com.shikkhokplus.app.feature.pay.PayOption
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** G1 rendered: the switcher, paying, and Back after a switch [BR4.2]. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class GuardianHomeScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun loaded(vararg names: String): GuardianUiState.Loaded =
        GuardianStateMapper.afterLoad(GuardianHomeDto(names.map { childDto(it) }), null) as GuardianUiState.Loaded

    @Test
    fun `one child draws no switcher, and Pay pays that child's fee`() {
        val paid = mutableListOf<PayOption>()
        compose.setContent {
            ShikkhokTheme { GuardianHomeScreen(loaded("Tasnim"), GuardianActions(onPay = { paid += it })) }
        }

        compose.onNodeWithTag(TAG_GUARDIAN_SWITCHER).assertDoesNotExist()
        compose.onNodeWithTag(TAG_GUARDIAN_PAY).performScrollTo().performClick()

        assertEquals("seat-Tasnim", paid.single().enrollmentId)
    }

    @Test
    fun `a guardian reaching nothing is told so rather than shown a blank`() {
        compose.setContent { ShikkhokTheme { GuardianHomeScreen(GuardianUiState.Empty(null), GuardianActions()) } }

        compose.onNodeWithTag(TAG_GUARDIAN_EMPTY).assertExists()
    }

    @Test
    fun `BACK AFTER A CHILD SWITCH does not reach the previous child`() {
        // [NFR23.6, NFR14.30, BR4.2, AC9.4.2]. A switcher implemented as
        // a navigation push would leave the previous child on the back
        // stack, so Back would land in another child's figures. Two
        // halves: the switch replaced (1), and Back reaches nothing (2).
        var state by mutableStateOf(loaded("Rahim", "Karima"))
        compose.setContent {
            ShikkhokTheme {
                GuardianHomeScreen(state, GuardianActions(onSelect = { state = GuardianStateMapper.select(state, it) }))
            }
        }
        assertEquals("Rahim", selectedChildName())

        compose.onAllNodesWithTag(TAG_GUARDIAN_CHIP)[1].performClick()
        compose.waitForIdle()
        assertEquals("Karima", selectedChildName())

        compose.activityRule.scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        compose.waitForIdle()
        assertEquals("Karima", selectedChildName())
    }

    /**
     * The name in the shown-child block, read by its tag: both names are
     * on screen as switcher chips, so a text query would be ambiguous.
     *
     * @return The shown child's name
     */
    private fun selectedChildName(): String =
        compose
            .onNodeWithTag(TAG_GUARDIAN_SELECTED_NAME, useUnmergedTree = true)
            .fetchSemanticsNode()
            .config[SemanticsProperties.Text]
            .joinToString("") { it.text }
}
