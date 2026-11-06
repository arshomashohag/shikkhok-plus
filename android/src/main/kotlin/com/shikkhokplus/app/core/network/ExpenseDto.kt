package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One expense as the server returns it.
 *
 * `amount` is [Money], so a JSON **number** fails loudly rather than
 * being accepted and converted.
 *
 * @property expenseId The expense
 * @property category One of the closed set, such as `printing`
 * @property what What it was
 * @property amount How much
 * @property spentOn The day it was paid, `yyyy-MM-dd`
 * @property payee Who was paid, or null
 * @property note A note or receipt number, or null
 * @property voided Whether it was voided; a voided expense counts for nothing
 * @property voidReason Why it was voided, or null
 */
@Serializable
data class ExpenseDto(
    @SerialName("expense_id") val expenseId: String,
    @SerialName("category") val category: String,
    @SerialName("what") val what: String,
    @SerialName("amount") val amount: Money,
    @SerialName("spent_on") val spentOn: String,
    @SerialName("payee") val payee: String? = null,
    @SerialName("note") val note: String? = null,
    @SerialName("voided") val voided: Boolean = false,
    @SerialName("void_reason") val voidReason: String? = null,
)

/**
 * A total for one category, as the server summed it.
 *
 * @property category The category
 * @property total What was spent in it, voided expenses excluded
 */
@Serializable
data class CategoryTotalDto(
    @SerialName("category") val category: String,
    @SerialName("total") val total: Money,
)

/**
 * One month of expenses: `GET /v1/expenses?month=`.
 *
 * @property month The month, `YYYY-MM`
 * @property total What was spent, voided expenses excluded
 * @property byCategory The total per category
 * @property expenses Every expense recorded for the month, voided included
 */
@Serializable
data class ExpenseMonthDto(
    @SerialName("month") val month: String,
    @SerialName("total") val total: Money,
    @SerialName("by_category") val byCategory: List<CategoryTotalDto> = emptyList(),
    @SerialName("expenses") val expenses: List<ExpenseDto> = emptyList(),
)

/**
 * The body of `POST /v1/expenses`.
 *
 * @property category The category
 * @property what What it was
 * @property amount How much, as the wire string
 * @property spentOn The day it was paid
 * @property payee Who was paid, or null
 * @property note A note or receipt number, or null
 * @property clientMutationId The retry key: a resend under it is a replay
 */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class ExpenseRequestDto(
    @SerialName("category") val category: String,
    @SerialName("what") val what: String,
    @SerialName("amount") val amount: Money,
    @SerialName("spent_on") val spentOn: String,
    @SerialName("payee") val payee: String? = null,
    @SerialName("note") val note: String? = null,
    @EncodeDefault @SerialName("client_mutation_id") val clientMutationId: String,
)

/**
 * The body of `POST /v1/expenses/{id}/void`.
 *
 * @property reason Why, or null
 */
@Serializable
data class ExpenseVoidRequestDto(
    @SerialName("reason") val reason: String? = null,
)

/**
 * What came in, by purpose.
 *
 * @property monthly Monthly fees
 * @property exam Exam fees
 * @property other Other fees
 * @property total All three
 */
@Serializable
data class MoneyCollectedDto(
    @SerialName("monthly") val monthly: Money,
    @SerialName("exam") val exam: Money,
    @SerialName("other") val other: Money,
    @SerialName("total") val total: Money,
)

/**
 * One exam or other fee's takings against what was spent for it.
 *
 * @property extraFeeId The fee
 * @property label Its name
 * @property collected What came in for it this month
 * @property spent What was spent for it this month
 */
@Serializable
data class MoneyFeeLineDto(
    @SerialName("extra_fee_id") val extraFeeId: String,
    @SerialName("label") val label: String,
    @SerialName("collected") val collected: Money,
    @SerialName("spent") val spent: Money,
)

/**
 * The month's money in and out: `GET /v1/money/summary?month=`.
 *
 * Every figure and the verdict are the server's [TC-9]: the client
 * neither subtracts nor compares.
 *
 * @property month The month, `YYYY-MM`
 * @property collected What came in, by purpose
 * @property spentTotal What went out
 * @property spentByCategory What went out, by category
 * @property net The difference, without a sign
 * @property netKind `surplus`, `deficit` or `even`
 * @property owedMonthly Monthly fees still owed today
 * @property owedExtra Exam and other fees still owed today
 * @property extraFees Each extra fee's takings against its spending
 */
@Serializable
data class MoneySummaryDto(
    @SerialName("month") val month: String,
    @SerialName("collected") val collected: MoneyCollectedDto,
    @SerialName("spent_total") val spentTotal: Money,
    @SerialName("spent_by_category") val spentByCategory: List<CategoryTotalDto> = emptyList(),
    @SerialName("net") val net: Money,
    @SerialName("net_kind") val netKind: String,
    @SerialName("owed_monthly") val owedMonthly: Money,
    @SerialName("owed_extra") val owedExtra: Money,
    @SerialName("extra_fees") val extraFees: List<MoneyFeeLineDto> = emptyList(),
)
