package com.shikkhokplus.app.feature.dashboard

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.dashboard.ui.DashboardActions
import com.shikkhokplus.app.feature.dashboard.ui.DashboardScreen
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_ATTENDANCE_BAR
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_AVERAGE_LEGEND
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_BATCH_CHIP
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_ERROR
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_FEE_HISTORY
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_FEE_MONTH
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_LOADING
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_CHILD_CHIP
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_EXAM_CHART
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_EXAMS_EMPTY
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_HIGHEST_LEGEND
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_LATEST_EXAM
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_RANGE_CHIP
import com.shikkhokplus.app.feature.dashboard.ui.TAG_DASHBOARD_SEND_MONEY
import com.shikkhokplus.app.feature.dashboard.ui.attendanceBarHeight
import com.shikkhokplus.app.feature.dashboard.ui.marksSeries
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** What the dashboard renders for a given state (D1, D2). */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class DashboardScreenTest {
    @get:Rule
    val compose = createComposeRule()

    private fun state(
        reader: DashboardReader = DashboardReader.TEACHER,
        exams: List<com.shikkhokplus.app.core.network.DashboardExamDto> = listOf(examDto(), examDto("x2", 60, 55, 90)),
        children: List<DashboardChild> = emptyList(),
    ) = DashboardUiState.Loaded(
        reader = reader,
        heading = "Sadia Islam",
        subheading = "Class 9 Physics",
        range = DashboardRange.SIX_MONTHS,
        children = children,
        selectedChild = children.firstOrNull()?.key,
        batches = children.firstOrNull()?.batches.orEmpty(),
        seat = "e-1",
        attendancePercent = 86,
        present = 43,
        held = 50,
        examAveragePercent = if (exams.isEmpty()) null else 74,
        direction = DashboardDirection.UP,
        owed = Money.of("2000.00"),
        attendance = dashboardDto().attendanceByMonth,
        exams = exams,
        feeMonths = listOf(DashboardFeeMonth("2026-10", com.shikkhokplus.app.feature.fees.StripKind.PAID)),
    )

    @Test
    fun average_and_highest_lines_hidden_when_null() {
        val exams = listOf(examDto("a", 81, null, null), examDto("b", 60, null, null))
        compose.setContent { DashboardScreen(state(exams = exams), DashboardActions()) }

        compose.onNodeWithTag(TAG_DASHBOARD_EXAM_CHART).assertExists()
        compose.onNodeWithTag(TAG_DASHBOARD_AVERAGE_LEGEND).assertDoesNotExist()
        compose.onNodeWithTag(TAG_DASHBOARD_HIGHEST_LEGEND).assertDoesNotExist()
        assertFalse(marksSeries(exams).hasAverage)
        assertFalse(marksSeries(exams).hasHighest)
    }

    @Test
    fun `average and highest lines show when the server sent them`() {
        compose.setContent { DashboardScreen(state(), DashboardActions()) }

        compose.onNodeWithTag(TAG_DASHBOARD_AVERAGE_LEGEND).assertExists()
        compose.onNodeWithTag(TAG_DASHBOARD_HIGHEST_LEGEND).assertExists()
        compose.onNodeWithTag(TAG_DASHBOARD_LATEST_EXAM).assertExists()
    }

    @Test
    fun empty_exams_shows_empty_state() {
        compose.setContent { DashboardScreen(state(exams = emptyList()), DashboardActions()) }

        compose.onNodeWithTag(TAG_DASHBOARD_EXAMS_EMPTY).assertExists()
        compose.onNodeWithTag(TAG_DASHBOARD_EXAM_CHART).assertDoesNotExist()
    }

    @Test
    fun `series positions are the server's marks over the total and an absence is a gap`() {
        val series = marksSeries(listOf(examDto("a", 50, 25, 100), examDto("b", null, null, null)))

        assertEquals(listOf(0.5f, null), series.own)
        assertEquals(listOf(0.25f, null), series.average)
        assertEquals(listOf(1.0f, null), series.highest)
        assertNull(series.own[1])
        assertTrue(series.hasAverage)
    }

    @Test
    fun `bars are the server percent times the chart height and nothing else`() {
        assertEquals(60.dp, attendanceBarHeight(50, 120.dp))
        assertEquals(0.dp, attendanceBarHeight(null, 120.dp))
        assertEquals(120.dp, attendanceBarHeight(250, 120.dp))
    }

    @Test
    fun `a range chip tap reports the range`() {
        var chosen: DashboardRange? = null
        compose.setContent {
            DashboardScreen(state(), DashboardActions(onRange = { chosen = it }))
        }

        compose.onAllNodesWithTag(TAG_DASHBOARD_RANGE_CHIP)[1].performClick()

        assertEquals(DashboardRange.YEAR, chosen)
    }

    @Test
    fun `a guardian sees child chips and send money, a teacher does not`() {
        val kids = guardianHome().children.map { c -> DashboardChild(c.key, c.displayName, emptyList()) }
        var sent = false
        compose.setContent {
            DashboardScreen(
                state(reader = DashboardReader.GUARDIAN, children = kids),
                DashboardActions(onSendMoney = { sent = true }),
            )
        }

        compose.onAllNodesWithTag(TAG_DASHBOARD_CHILD_CHIP)[1].assertExists()
        compose.onNodeWithTag(TAG_DASHBOARD_SEND_MONEY).performScrollTo().performClick()
        assertTrue(sent)
    }

    @Test
    fun `a teacher has no send money`() {
        compose.setContent { DashboardScreen(state(), DashboardActions()) }

        compose.onNodeWithTag(TAG_DASHBOARD_SEND_MONEY).assertDoesNotExist()
    }

    @Test
    fun `loading and failure render their own states`() {
        val state = androidx.compose.runtime.mutableStateOf<DashboardUiState>(DashboardUiState.Loading)
        compose.setContent { DashboardScreen(state.value, DashboardActions()) }
        compose.onNodeWithTag(TAG_DASHBOARD_LOADING).assertExists()

        state.value = DashboardUiState.Failed("error.network.unreachable", retryable = true)
        compose.waitForIdle()
        compose.onNodeWithTag(TAG_DASHBOARD_ERROR).assertExists()
    }

    @Test
    fun `batch chips show for a child with several batches and report the seat`() {
        val kid =
            DashboardChild(
                "s-1",
                "Tanvir",
                listOf(DashboardBatch("s-1", "Physics"), DashboardBatch("s-2", "Math")),
            )
        var seat: String? = null
        var child: String? = null
        var history = false
        compose.setContent {
            DashboardScreen(
                state(reader = DashboardReader.GUARDIAN, children = listOf(kid, kid.copy(key = "s-9"))),
                DashboardActions(onBatch = { seat = it }, onChild = { child = it }, onFeeHistory = { history = true }),
            )
        }

        compose.onAllNodesWithTag(TAG_DASHBOARD_BATCH_CHIP)[1].performClick()
        compose.onAllNodesWithTag(TAG_DASHBOARD_CHILD_CHIP)[1].performClick()
        compose.onNodeWithTag(TAG_DASHBOARD_FEE_HISTORY).performScrollTo().performClick()

        assertEquals("s-2", seat)
        assertEquals("s-9", child)
        assertTrue(history)
        compose.onAllNodesWithTag(TAG_DASHBOARD_FEE_MONTH).assertCountEquals(1)
        compose.onAllNodesWithTag(TAG_DASHBOARD_ATTENDANCE_BAR).assertCountEquals(2)
    }

    @Test
    fun `the dashboard route carries the reader and the encoded names`() {
        assertEquals(
            "dashboard/e-1?reader=GUARDIAN&child=Tan+vir&batch=Class+9",
            com.shikkhokplus.app.navigation.Destination.Dashboard.of("e-1", "GUARDIAN", "Tan vir", "Class 9"),
        )
    }

    @Test
    fun `a guardian's title names the child, and the subtitle only the batch`() {
        // G2: "তাসনিম's progress" -- the child is the screen's subject.
        compose.setContent { DashboardScreen(state(reader = DashboardReader.GUARDIAN), DashboardActions()) }

        compose.onNodeWithText("Sadia's progress").assertExists()
        compose.onNodeWithText("Class 9 Physics").assertExists()
    }

    @Test
    fun `the teacher dashboard heading names the student and the batch`() {
        compose.setContent { DashboardScreen(state(), DashboardActions()) }

        compose.onNodeWithText("Sadia Islam · Class 9 Physics").assertExists()
    }

    @Test
    fun `the fee history route carries the names on to the dashboard`() {
        assertEquals(
            "fees/e-1?reader=TEACHER&child=Sadia+Islam&batch=Class+9",
            com.shikkhokplus.app.navigation.Destination.FeeHistory.of("e-1", "TEACHER", "Sadia Islam", "Class 9"),
        )
        assertEquals(
            "fees/e-1?reader=STUDENT&child=&batch=",
            com.shikkhokplus.app.navigation.Destination.FeeHistory.of("e-1", "STUDENT"),
        )
    }
}
