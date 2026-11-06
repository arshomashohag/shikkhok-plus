package com.shikkhokplus.app.feature.expenses

import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.network.CategoryTotalDto
import com.shikkhokplus.app.core.network.ExpenseMonthDto
import com.shikkhokplus.app.core.network.MoneySummaryDto

/** The message key for a request that never got an answer. */
internal const val OFFLINE_KEY: String = "error.network.unreachable"

/** The longest description the server stores. */
internal const val EXPENSE_WHAT_MAX: Int = 120

/** The longest payee the server stores. */
internal const val EXPENSE_PAYEE_MAX: Int = 80

/** The longest note or void reason the server stores. */
internal const val EXPENSE_NOTE_MAX: Int = 200

/**
 * Map one month of expenses to what the list draws.
 *
 * @param dto The server's month
 * @return Empty when nothing was recorded, else the rows and totals
 */
internal fun expensesBodyOf(dto: ExpenseMonthDto): ExpensesBody =
    if (dto.expenses.isEmpty()) {
        ExpensesBody.Empty
    } else {
        ExpensesBody.Loaded(
            total = dto.total,
            rows =
                dto.expenses.map {
                    ExpenseRow(
                        expenseId = it.expenseId,
                        category = ExpenseCategory.fromWire(it.category),
                        what = it.what,
                        amount = it.amount,
                        spentOn = it.spentOn,
                        payee = it.payee?.takeIf(String::isNotBlank),
                        voided = it.voided,
                        voidReason = it.voidReason?.takeIf(String::isNotBlank),
                    )
                },
            byCategory = dto.byCategory.map(::categoryTotalOf),
        )
    }

/**
 * Map the server's summary, figure for figure.
 *
 * @param dto The server's summary
 * @return The summary the screen draws
 */
internal fun summaryOf(dto: MoneySummaryDto): MoneySummary =
    MoneySummary(
        collectedMonthly = dto.collected.monthly,
        collectedExam = dto.collected.exam,
        collectedOther = dto.collected.other,
        collectedTotal = dto.collected.total,
        spentTotal = dto.spentTotal,
        spentByCategory = dto.spentByCategory.map(::categoryTotalOf),
        net = dto.net,
        netKind = NetKind.fromWire(dto.netKind),
        owedMonthly = dto.owedMonthly,
        owedExtra = dto.owedExtra,
        fees = dto.extraFees.map { SummaryFeeLine(it.extraFeeId, it.label, it.collected, it.spent) },
    )

/**
 * Move a month by some number of months.
 *
 * @param month `YYYY-MM`
 * @param by How many months, negative for earlier
 * @return The moved month, or [month] unchanged if it does not parse
 */
internal fun shiftMonth(month: String, by: Long): String =
    YearMonth.parseOrNull(month)?.plusMonths(by)?.toString() ?: month

private fun categoryTotalOf(dto: CategoryTotalDto): CategoryTotal =
    CategoryTotal(ExpenseCategory.fromWire(dto.category), dto.total)
