package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.expenses.ExpenseDraft
import com.shikkhokplus.app.feature.expenses.ExpensesRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody

/**
 * Expenses and the monthly summary, over HTTP.
 *
 * The server validates every field and answers a refusal with its one
 * error envelope; nothing here checks a value beyond sending it.
 *
 * @property client The authenticated HTTP client
 */
class HttpExpensesRepository(
    private val client: HttpClient,
) : ExpensesRepository {

    override suspend fun month(month: String): AuthResult<ExpenseMonthDto> =
        call { client.get("/v1/expenses") { parameter("month", month) } }

    override suspend fun record(draft: ExpenseDraft): AuthResult<ExpenseDto> =
        call {
            client.post("/v1/expenses") {
                setBody(
                    ExpenseRequestDto(
                        category = draft.category.wire,
                        what = draft.what,
                        amount = draft.amount,
                        spentOn = draft.spentOn,
                        payee = draft.payee,
                        note = draft.note,
                        clientMutationId = draft.clientMutationId,
                    ),
                )
            }
        }

    override suspend fun void(expenseId: String, reason: String?): AuthResult<ExpenseDto> =
        call { client.post("/v1/expenses/$expenseId/void") { setBody(ExpenseVoidRequestDto(reason)) } }

    override suspend fun summary(month: String): AuthResult<MoneySummaryDto> =
        call { client.get("/v1/money/summary") { parameter("month", month) } }
}
