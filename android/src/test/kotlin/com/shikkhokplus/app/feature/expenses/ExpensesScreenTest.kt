package com.shikkhokplus.app.feature.expenses

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.expenses.ui.ExpensesActions
import com.shikkhokplus.app.feature.expenses.ui.ExpensesScreen
import com.shikkhokplus.app.feature.expenses.ui.RecordExpenseScreen
import com.shikkhokplus.app.feature.expenses.ui.SummaryScreen
import com.shikkhokplus.app.feature.expenses.ui.TAG_EXPENSES_EMPTY
import com.shikkhokplus.app.feature.expenses.ui.TAG_EXPENSES_VOID_CONFIRM
import com.shikkhokplus.app.feature.expenses.ui.TAG_EXPENSES_VOID_REASON
import com.shikkhokplus.app.feature.expenses.ui.TAG_EXPENSE_SAVE
import com.shikkhokplus.app.feature.expenses.ui.TAG_MONTH_NEXT
import com.shikkhokplus.app.feature.expenses.ui.TAG_MONTH_PREVIOUS
import com.shikkhokplus.app.feature.expenses.ui.expenseVoidTag
import com.shikkhokplus.app.feature.expenses.ui.summaryFeeTag
import com.shikkhokplus.app.feature.expenses.ui.SummaryActions
import com.shikkhokplus.app.feature.expenses.ui.RecordExpenseActions
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** Expenses, recording one, and the summary, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ExpensesScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val live =
        ExpenseRow(
            expenseId = "x1",
            category = ExpenseCategory.PRINTING,
            what = "Question papers",
            amount = Money.of("450.00"),
            spentOn = "2026-11-03",
            payee = null,
            voided = false,
            voidReason = null,
        )
    private val voided =
        ExpenseRow(
            expenseId = "x2",
            category = ExpenseCategory.RENT,
            what = "Old rent",
            amount = Money.of("4000.00"),
            spentOn = "2026-11-01",
            payee = null,
            voided = true,
            voidReason = "Typed twice",
        )

    @Test
    fun `a month lists its expenses and only a live one can be voided`() {
        val voids = mutableListOf<Pair<String, String>>()
        compose.setContent {
            ExpensesScreen(
                state =
                    ExpensesUiState(
                        month = "2026-11",
                        canGoForward = false,
                        body =
                            ExpensesBody.Loaded(
                                total = Money.of("450.00"),
                                rows = listOf(live, voided),
                                byCategory = listOf(CategoryTotal(ExpenseCategory.PRINTING, Money.of("450.00"))),
                            ),
                    ),
                actions = ExpensesActions(onVoid = { id, reason -> voids += id to reason }),
            )
        }

        compose.onNodeWithText("Question papers").assertIsDisplayed()
        compose.onNodeWithText("Voided · Typed twice").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(expenseVoidTag("x2")).assertDoesNotExist()

        compose.onNodeWithTag(expenseVoidTag("x1")).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_EXPENSES_VOID_REASON).performTextInput("Duplicate")
        compose.onNodeWithTag(TAG_EXPENSES_VOID_CONFIRM).performClick()

        assertEquals(listOf("x1" to "Duplicate"), voids)
    }

    @Test
    fun `the next month cannot be reached from the current one`() {
        val shifts = mutableListOf<Long>()
        compose.setContent {
            ExpensesScreen(
                state = ExpensesUiState(month = "2026-11", canGoForward = false, body = ExpensesBody.Empty),
                actions = ExpensesActions(onShift = { shifts += it }),
            )
        }

        compose.onNodeWithTag(TAG_EXPENSES_EMPTY).assertIsDisplayed()
        compose.onNodeWithTag(TAG_MONTH_NEXT).assertIsNotEnabled()
        compose.onNodeWithTag(TAG_MONTH_PREVIOUS).performClick()
        assertEquals(listOf(-1L), shifts)
    }

    @Test
    fun `the record form saves only once it can be sent`() {
        var saves = 0
        compose.setContent {
            RecordExpenseScreen(
                state = RecordExpenseUiState(spentOn = "2026-11-06"),
                actions = RecordExpenseActions(onSave = { saves++ }),
            )
        }
        compose.onNodeWithTag(TAG_EXPENSE_SAVE).performScrollTo().assertIsNotEnabled()
        assertEquals(0, saves)
    }

    @Test
    fun `a complete record form can be saved`() {
        var saves = 0
        compose.setContent {
            RecordExpenseScreen(
                state = RecordExpenseUiState(what = "Chalk", typedAmount = "120", spentOn = "2026-11-06"),
                actions = RecordExpenseActions(onSave = { saves++ }),
            )
        }
        compose.onNodeWithTag(TAG_EXPENSE_SAVE).performScrollTo().assertIsEnabled().performClick()
        assertEquals(1, saves)
    }

    @Test
    fun `the summary names the server's verdict and each fee's line`() {
        val summary =
            MoneySummary(
                collectedMonthly = Money.of("3000.00"),
                collectedExam = Money.of("500.00"),
                collectedOther = Money.ZERO,
                collectedTotal = Money.of("3500.00"),
                spentTotal = Money.of("4000.00"),
                spentByCategory = emptyList(),
                net = Money.of("500.00"),
                netKind = NetKind.DEFICIT,
                owedMonthly = Money.of("1200.00"),
                owedExtra = Money.of("200.00"),
                fees = listOf(SummaryFeeLine("f1", "Half-yearly exam", Money.of("500.00"), Money.of("300.00"))),
            )
        compose.setContent {
            SummaryScreen(
                state = SummaryUiState(month = "2026-11", canGoForward = false, body = SummaryBody.Loaded(summary)),
                actions = SummaryActions(),
            )
        }

        compose.onNodeWithText("Spent more than collected").assertIsDisplayed()
        compose.onNodeWithTag(summaryFeeTag("f1")).performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("Collected ৳500 · spent ৳300").assertIsDisplayed()
    }
}
