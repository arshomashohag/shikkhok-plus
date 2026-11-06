package com.shikkhokplus.app.feature.expenses

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ExpenseDto
import com.shikkhokplus.app.core.network.ExpenseMonthDto
import com.shikkhokplus.app.core.network.MoneySummaryDto
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * The closed set of expense categories, in the order the form offers them.
 *
 * @property wire The value the server uses
 */
enum class ExpenseCategory(val wire: String) {
    /** Exam paper. */
    EXAM_PAPER("exam_paper"),

    /** Printing. */
    PRINTING("printing"),

    /** Rent. */
    RENT("rent"),

    /** Utilities. */
    UTILITIES("utilities"),

    /** Materials. */
    MATERIALS("materials"),

    /** Transport. */
    TRANSPORT("transport"),

    /** Salary. */
    SALARY("salary"),

    /** Anything else. */
    OTHER("other"),
    ;

    companion object {
        /**
         * Read the server's value.
         *
         * @param wire The server's `category`
         * @return The category; one this build does not know reads as other
         */
        fun fromWire(wire: String): ExpenseCategory = entries.firstOrNull { it.wire == wire } ?: OTHER
    }
}

/**
 * What the owner typed for one expense; the server validates it.
 *
 * @property category What it was spent on
 * @property what What it was
 * @property amount How much
 * @property spentOn The day it was paid, `yyyy-MM-dd`
 * @property payee Who was paid, or null
 * @property note A note or receipt number, or null
 * @property clientMutationId One per opened form, reused on a resend
 */
data class ExpenseDraft(
    val category: ExpenseCategory,
    val what: String,
    val amount: Money,
    val spentOn: String,
    val payee: String?,
    val note: String?,
    val clientMutationId: String,
)

/** What the expense and summary screens need from the network. */
interface ExpensesRepository {
    /**
     * Read one month's expenses.
     *
     * @param month `YYYY-MM`
     * @return The month, a refusal, or a transport failure
     */
    suspend fun month(month: String): AuthResult<ExpenseMonthDto>

    /**
     * Record an expense.
     *
     * @param draft What was typed
     * @return The stored expense, a refusal, or a transport failure
     */
    suspend fun record(draft: ExpenseDraft): AuthResult<ExpenseDto>

    /**
     * Void an expense; it stays listed and counts for nothing.
     *
     * @param expenseId The expense
     * @param reason Why, or null
     * @return The voided expense, a refusal, or a transport failure
     */
    suspend fun void(expenseId: String, reason: String?): AuthResult<ExpenseDto>

    /**
     * Read the month's money in and out.
     *
     * @param month `YYYY-MM`
     * @return The summary, a refusal, or a transport failure
     */
    suspend fun summary(month: String): AuthResult<MoneySummaryDto>
}
