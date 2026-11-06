package com.shikkhokplus.app.feature.expenses

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.CategoryTotalDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.ExpenseDto
import com.shikkhokplus.app.core.network.ExpenseMonthDto
import com.shikkhokplus.app.core.network.MoneyCollectedDto
import com.shikkhokplus.app.core.network.MoneyFeeLineDto
import com.shikkhokplus.app.core.network.MoneySummaryDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** A scripted [ExpensesRepository] that records what it was asked. */
class FakeExpensesRepository : ExpensesRepository {
    var monthResults: MutableList<AuthResult<ExpenseMonthDto>> = mutableListOf(AuthResult.Ok(emptyMonth()))
    var recordResult: AuthResult<ExpenseDto> = AuthResult.Ok(expense())
    var voidResult: AuthResult<ExpenseDto> = AuthResult.Ok(expense(voided = true))
    var summaryResult: AuthResult<MoneySummaryDto> = AuthResult.Ok(summary())
    val monthsRead: MutableList<String> = mutableListOf()
    val summariesRead: MutableList<String> = mutableListOf()
    val recorded: MutableList<ExpenseDraft> = mutableListOf()
    val voided: MutableList<Pair<String, String?>> = mutableListOf()

    override suspend fun month(month: String): AuthResult<ExpenseMonthDto> {
        monthsRead += month
        return if (monthResults.size > 1) monthResults.removeAt(0) else monthResults.first()
    }

    override suspend fun record(draft: ExpenseDraft): AuthResult<ExpenseDto> {
        recorded += draft
        return recordResult
    }

    override suspend fun void(expenseId: String, reason: String?): AuthResult<ExpenseDto> {
        voided += expenseId to reason
        return voidResult
    }

    override suspend fun summary(month: String): AuthResult<MoneySummaryDto> {
        summariesRead += month
        return summaryResult
    }

    companion object {
        fun expense(
            id: String = "x1",
            voided: Boolean = false,
            category: String = "printing",
            amount: String = "450.00",
        ) = ExpenseDto(
            expenseId = id,
            category = category,
            what = "Question papers",
            amount = Money.of(amount),
            spentOn = "2026-11-03",
            payee = "Nilkhet Press",
            note = null,
            voided = voided,
            voidReason = if (voided) "Typed twice" else null,
        )

        fun emptyMonth(month: String = "2026-11") = ExpenseMonthDto(month, Money.ZERO, emptyList(), emptyList())

        fun month(vararg expenses: ExpenseDto, total: String = "450.00") =
            ExpenseMonthDto(
                month = "2026-11",
                total = Money.of(total),
                byCategory = listOf(CategoryTotalDto("printing", Money.of(total))),
                expenses = expenses.toList(),
            )

        fun summary(netKind: String = "deficit") =
            MoneySummaryDto(
                month = "2026-11",
                collected =
                    MoneyCollectedDto(
                        monthly = Money.of("3000.00"),
                        exam = Money.of("500.00"),
                        other = Money.ZERO,
                        total = Money.of("3500.00"),
                    ),
                spentTotal = Money.of("4000.00"),
                spentByCategory = listOf(CategoryTotalDto("rent", Money.of("4000.00"))),
                net = Money.of("500.00"),
                netKind = netKind,
                owedMonthly = Money.of("1200.00"),
                owedExtra = Money.of("200.00"),
                extraFees = listOf(MoneyFeeLineDto("f1", "Half-yearly exam", Money.of("500.00"), Money.of("300.00"))),
            )

        fun refusal(key: String, retryable: Boolean = false) =
            AuthResult.Refused(ErrorEnvelope(ErrorBody("X", retryable, key)))
    }
}
