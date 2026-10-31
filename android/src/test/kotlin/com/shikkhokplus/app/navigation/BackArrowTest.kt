package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.designsystem.TAG_SCAFFOLD_BACK
import com.shikkhokplus.app.feature.attendance.AttendanceUiState
import com.shikkhokplus.app.feature.attendance.ui.AttendanceScreen
import com.shikkhokplus.app.feature.fees.FeeUiState
import com.shikkhokplus.app.feature.fees.ui.FeeHistoryScreen
import com.shikkhokplus.app.feature.marks.MarksUiState
import com.shikkhokplus.app.feature.marks.ui.ExamListScreen
import com.shikkhokplus.app.feature.marks.ui.MarksheetScreen
import com.shikkhokplus.app.feature.marks.ui.ProgressScreen
import com.shikkhokplus.app.feature.sessions.SessionsUiState
import com.shikkhokplus.app.feature.sessions.ui.SessionListScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * Every pushed screen draws a back arrow that calls its `onBack`.
 *
 * The screens were reachable with no way back except the system
 * gesture; each is rendered with a recording callback and the arrow
 * clicked once.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class BackArrowTest {

    @get:Rule
    val compose = createComposeRule()

    private fun assertBackArrowCalls(screen: @Composable (onBack: () -> Unit) -> Unit) {
        var calls = 0
        compose.setContent { ShikkhokTheme { screen { calls++ } } }
        compose.onNodeWithTag(TAG_SCAFFOLD_BACK).performClick()
        assertEquals(1, calls)
    }

    @Test
    fun `marksheet back arrow calls onBack`() =
        assertBackArrowCalls { MarksheetScreen(state = MarksUiState.Loading, onBack = it) }

    @Test
    fun `progress back arrow calls onBack`() =
        assertBackArrowCalls { ProgressScreen(state = MarksUiState.Loading, onBack = it) }

    @Test
    fun `fee history back arrow calls onBack`() =
        assertBackArrowCalls {
            FeeHistoryScreen(state = FeeUiState.Loading, onRetry = {}, onBack = it)
        }

    @Test
    fun `sessions back arrow calls onBack`() =
        assertBackArrowCalls {
            SessionListScreen(state = SessionsUiState.Loading, onOpen = {}, onBack = it)
        }

    @Test
    fun `attendance back arrow calls onBack`() =
        assertBackArrowCalls { AttendanceScreen(state = AttendanceUiState.Loading, onBack = it) }

    @Test
    fun `exam list back arrow calls onBack`() =
        assertBackArrowCalls {
            ExamListScreen(state = MarksUiState.Loading, onOpen = {}, onBack = it)
        }
}
