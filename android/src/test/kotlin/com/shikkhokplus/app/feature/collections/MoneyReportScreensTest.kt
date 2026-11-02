package com.shikkhokplus.app.feature.collections

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.collections.ui.BatchMonthActions
import com.shikkhokplus.app.feature.collections.ui.BatchMonthScreen
import com.shikkhokplus.app.feature.collections.ui.CollectionsActions
import com.shikkhokplus.app.feature.collections.ui.CollectionsScreen
import com.shikkhokplus.app.feature.collections.ui.TAG_BATCH_MONTH_FILTER
import com.shikkhokplus.app.feature.collections.ui.TAG_BATCH_MONTH_NEXT
import com.shikkhokplus.app.feature.collections.ui.TAG_BATCH_MONTH_SEAT
import com.shikkhokplus.app.feature.collections.ui.TAG_COLLECTIONS_BATCH_ROW
import com.shikkhokplus.app.feature.collections.ui.TAG_COLLECTIONS_CHIP
import com.shikkhokplus.app.feature.collections.ui.TAG_COLLECTIONS_MONTH
import com.shikkhokplus.app.feature.collections.ui.barHeight
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** What the money report screens render for a given state. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MoneyReportScreensTest {
    @get:Rule
    val compose = createComposeRule()

    private val loaded =
        CollectionsUiState.Loaded(
            batches = listOf(BatchChip("b-1", "Physics", false), BatchChip("b-2", "Math", true)),
            months =
                listOf(
                    MonthBar("2026-10", Money.of("1000.00"), Money.of("600.00"), 100, 60, false),
                    MonthBar("2026-11", Money.of("1000.00"), Money.ZERO, 100, 0, true),
                ),
            headlinePeriod = "2026-10",
            headlineCollected = Money.of("600.00"),
            headlineCharged = Money.of("1000.00"),
            outstanding = Money.of("9500.00"),
            owingStudents = 11,
            batchRows =
                listOf(
                    BatchMonthRow(
                        batchId = "b-1",
                        name = "Physics",
                        period = "2026-10",
                        collected = Money.of("600.00"),
                        charged = Money.of("1000.00"),
                        counts = SeatCounts(1, 0, 2),
                    ),
                ),
        )

    @Test
    fun `bars are the server percent times the chart height and nothing else`() {
        assertEquals(60.dp, barHeight(50))
        assertEquals(0.dp, barHeight(0))
        assertEquals(barHeight(100), barHeight(250))
    }

    @Test
    fun `the report shows a pair of bars per month, the chips and the batch rows`() {
        var toggled: String? = null
        var opened: BatchMonthRow? = null
        var month: String? = null
        compose.setContent {
            CollectionsScreen(
                loaded,
                CollectionsActions(
                    onToggleBatch = { toggled = it },
                    onOpenBatch = { opened = it },
                    onSelectMonth = { month = it },
                ),
            )
        }

        assertEquals(2, compose.onAllNodesWithTag(TAG_COLLECTIONS_MONTH).fetchSemanticsNodes().size)
        compose.onAllNodesWithTag(TAG_COLLECTIONS_CHIP)[0].performSemanticsAction(SemanticsActions.OnClick)
        compose.onAllNodesWithTag(TAG_COLLECTIONS_MONTH)[1].performSemanticsAction(SemanticsActions.OnClick)
        compose.onNodeWithTag(TAG_COLLECTIONS_BATCH_ROW).performSemanticsAction(SemanticsActions.OnClick)
        assertEquals("b-1", toggled)
        assertEquals("2026-11", month)
        assertEquals("b-1", opened?.batchId)
    }

    @Test
    fun `the month screen labels its filters with the server counts and offers next only when one exists`() {
        val state =
            BatchMonthUiState.Loaded(
                period = "2026-10",
                collected = Money.of("900.00"),
                charged = Money.of("1200.00"),
                counts = SeatCounts(paid = 9, checking = 1, owed = 2),
                filter = MonthFilter.ALL,
                seats =
                    listOf(
                        MonthSeat("e-1", "Sadia", SeatKind.OVERDUE, Money.of("1000.00"), 22, null, null),
                        MonthSeat("e-2", "Mitu", SeatKind.CHECKING, Money.of("0.00"), null, Money.of("1000.00"), null),
                    ),
                canGoNext = true,
            )
        var filtered: MonthFilter? = null
        compose.setContent {
            BatchMonthScreen("Physics", state, BatchMonthActions(onFilter = { filtered = it }))
        }

        assertEquals(4, compose.onAllNodesWithTag(TAG_BATCH_MONTH_FILTER).fetchSemanticsNodes().size)
        compose.onAllNodesWithTag(TAG_BATCH_MONTH_FILTER)[3].performSemanticsAction(SemanticsActions.OnClick)
        assertEquals(MonthFilter.OWED, filtered)
        assertEquals(2, compose.onAllNodesWithTag(TAG_BATCH_MONTH_SEAT).fetchSemanticsNodes().size)
        compose.onNodeWithTag(TAG_BATCH_MONTH_NEXT).assertIsDisplayed()
    }
}
