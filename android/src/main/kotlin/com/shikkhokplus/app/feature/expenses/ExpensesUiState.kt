package com.shikkhokplus.app.feature.expenses

import com.shikkhokplus.app.core.model.Money

/**
 * One expense as the list draws it.
 *
 * @property expenseId The expense
 * @property category What it was spent on
 * @property what What it was
 * @property amount How much
 * @property spentOn The day it was paid, `yyyy-MM-dd`
 * @property payee Who was paid, or null
 * @property voided Whether it was voided: drawn crossed out, with no void action
 * @property voidReason Why it was voided, or null
 */
data class ExpenseRow(
    val expenseId: String,
    val category: ExpenseCategory,
    val what: String,
    val amount: Money,
    val spentOn: String,
    val payee: String?,
    val voided: Boolean,
    val voidReason: String?,
)

/**
 * A category's total, as the server summed it.
 *
 * @property category The category
 * @property total What was spent in it
 */
data class CategoryTotal(val category: ExpenseCategory, val total: Money)

/** What the expense list renders below its month bar. */
sealed interface ExpensesBody {
    /** Waiting for the month. */
    data object Loading : ExpensesBody

    /** Nothing recorded for the month. */
    data object Empty : ExpensesBody

    /**
     * The month's expenses.
     *
     * @property total What was spent, as the server summed it
     * @property rows Every expense, voided included
     * @property byCategory The server's total per category
     */
    data class Loaded(
        val total: Money,
        val rows: List<ExpenseRow>,
        val byCategory: List<CategoryTotal>,
    ) : ExpensesBody

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : ExpensesBody
}

/**
 * The expense list.
 *
 * @property month The month shown, `YYYY-MM`
 * @property canGoForward False on the current month: there is nothing ahead
 * @property body The month's contents
 * @property voidFailedKey Message key when the last void failed, or null
 */
data class ExpensesUiState(
    val month: String,
    val canGoForward: Boolean,
    val body: ExpensesBody = ExpensesBody.Loading,
    val voidFailedKey: String? = null,
)

/**
 * One exam or other fee's line on the summary.
 *
 * @property extraFeeId The fee
 * @property label Its name
 * @property collected What came in for it
 * @property spent What was spent for it
 */
data class SummaryFeeLine(
    val extraFeeId: String,
    val label: String,
    val collected: Money,
    val spent: Money,
)

/** The server's verdict on the month, never computed here. */
enum class NetKind {
    /** More came in than went out. */
    SURPLUS,

    /** More went out than came in. */
    DEFICIT,

    /** The two were equal. */
    EVEN,
    ;

    companion object {
        /**
         * Read the server's value.
         *
         * @param wire The server's `net_kind`
         * @return The verdict; an unknown value reads as even, which claims nothing
         */
        fun fromWire(wire: String): NetKind =
            when (wire) {
                "surplus" -> SURPLUS
                "deficit" -> DEFICIT
                else -> EVEN
            }
    }
}

/**
 * The month's money in and out, every figure as the server sent it.
 *
 * @property collectedMonthly Monthly fees collected
 * @property collectedExam Exam fees collected
 * @property collectedOther Other fees collected
 * @property collectedTotal All collected
 * @property spentTotal All spent
 * @property spentByCategory Spent, by category
 * @property net The difference, unsigned
 * @property netKind Which way the difference goes
 * @property owedMonthly Monthly fees still owed today
 * @property owedExtra Exam and other fees still owed today
 * @property fees Each extra fee's line
 */
data class MoneySummary(
    val collectedMonthly: Money,
    val collectedExam: Money,
    val collectedOther: Money,
    val collectedTotal: Money,
    val spentTotal: Money,
    val spentByCategory: List<CategoryTotal>,
    val net: Money,
    val netKind: NetKind,
    val owedMonthly: Money,
    val owedExtra: Money,
    val fees: List<SummaryFeeLine>,
)

/** What the summary renders below its month bar. */
sealed interface SummaryBody {
    /** Waiting for the month. */
    data object Loading : SummaryBody

    /**
     * The month.
     *
     * @property summary The server's figures
     */
    data class Loaded(val summary: MoneySummary) : SummaryBody

    /**
     * The read failed.
     *
     * @property messageKey The server's key, or the offline key
     * @property retryable Whether to offer a retry
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : SummaryBody
}

/**
 * The monthly summary.
 *
 * @property month The month shown, `YYYY-MM`
 * @property canGoForward False on the current month
 * @property body The month's contents
 */
data class SummaryUiState(
    val month: String,
    val canGoForward: Boolean,
    val body: SummaryBody = SummaryBody.Loading,
)

/**
 * The record-an-expense form.
 *
 * @property category What it was spent on
 * @property what What it was
 * @property typedAmount The amount as typed
 * @property spentOn The day it was paid, `yyyy-MM-dd`
 * @property payee Who was paid
 * @property note A note or receipt number
 * @property saving Whether a save is in flight
 * @property saved Whether the server stored it; the route leaves on this
 * @property failureKey Message key for the last refusal, or null
 */
data class RecordExpenseUiState(
    val category: ExpenseCategory = ExpenseCategory.PRINTING,
    val what: String = "",
    val typedAmount: String = "",
    val spentOn: String,
    val payee: String = "",
    val note: String = "",
    val saving: Boolean = false,
    val saved: Boolean = false,
    val failureKey: String? = null,
) {
    /**
     * Whether the form can be sent: format only, the server decides the rest.
     *
     * A description and an amount that parses; whether the amount is
     * above zero, or the date in the past, is the server's to refuse.
     */
    val canSave: Boolean
        get() = !saving && what.isNotBlank() && Money.fromTyped(typedAmount) != null
}
