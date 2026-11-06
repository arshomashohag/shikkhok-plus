package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * A bonus or deduction on one salary line.
 *
 * @property adjustmentId The adjustment
 * @property kind `addition` or `deduction`
 * @property label What it is for
 * @property amount How much, always positive; [kind] says which way
 */
@Serializable
data class SalaryAdjustmentDto(
    @SerialName("adjustment_id") val adjustmentId: String,
    @SerialName("kind") val kind: String,
    @SerialName("label") val label: String,
    @SerialName("amount") val amount: Money,
)

/**
 * One payment against a salary line, recorded as an expense.
 *
 * @property expenseId The expense it was recorded as
 * @property amount How much
 * @property paidOn When, `yyyy-MM-dd`
 */
@Serializable
data class SalaryPaymentDto(
    @SerialName("expense_id") val expenseId: String,
    @SerialName("amount") val amount: Money,
    @SerialName("paid_on") val paidOn: String,
)

/**
 * One person's salary for one month. Every figure is the server's: the
 * base from the classes held, what is owed, paid and left.
 *
 * @property lineId The line
 * @property staffId Whose record it was drawn from
 * @property staffName Their name
 * @property centreName The centre paying it
 * @property period The month, `yyyy-MM`
 * @property basis `monthly` or `per_class`
 * @property rate The monthly salary or the per-class rate
 * @property classesHeld Classes held that month, for a per-class rate
 * @property base The salary before adjustments
 * @property adjustments Bonuses and deductions
 * @property owed What is owed after adjustments
 * @property paid What has been paid
 * @property remaining What is still owed
 * @property payments The payments recorded
 * @property status `draft` or `approved`
 */
@Serializable
data class SalaryLineDto(
    @SerialName("line_id") val lineId: String,
    @SerialName("staff_id") val staffId: String,
    @SerialName("staff_name") val staffName: String,
    @SerialName("centre_name") val centreName: String,
    @SerialName("period") val period: String,
    @SerialName("basis") val basis: String,
    @SerialName("rate") val rate: Money,
    @SerialName("classes_held") val classesHeld: Int = 0,
    @SerialName("base") val base: Money,
    @SerialName("adjustments") val adjustments: List<SalaryAdjustmentDto> = emptyList(),
    @SerialName("owed") val owed: Money,
    @SerialName("paid") val paid: Money,
    @SerialName("remaining") val remaining: Money,
    @SerialName("payments") val payments: List<SalaryPaymentDto> = emptyList(),
    @SerialName("status") val status: String,
) {
    /** Whether the line can still be adjusted and approved. */
    val draft: Boolean get() = status == "draft"
}

/**
 * The body of `POST /v1/centre/payroll/lines/{id}/adjustments`.
 *
 * @property kind `addition` or `deduction`
 * @property label What it is for
 * @property amount How much, positive
 */
@Serializable
data class AdjustmentBodyDto(
    @SerialName("kind") val kind: String,
    @SerialName("label") val label: String,
    @SerialName("amount") val amount: Money,
)

/**
 * The body of `POST /v1/centre/payroll/lines/{id}/payments`.
 *
 * @property amount How much, positive and at most what is left
 * @property clientMutationId The replay key, kept across a retry
 * @property paidOn When, or null for today
 * @property note A short note, or null
 */
@Serializable
data class SalaryPaymentBodyDto(
    @SerialName("amount") val amount: Money,
    @SerialName("client_mutation_id") val clientMutationId: String,
    @SerialName("paid_on") val paidOn: String? = null,
    @SerialName("note") val note: String? = null,
)
