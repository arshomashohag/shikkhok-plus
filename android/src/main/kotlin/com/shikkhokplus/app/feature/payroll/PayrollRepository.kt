package com.shikkhokplus.app.feature.payroll

import com.shikkhokplus.app.core.network.AdjustmentBodyDto
import com.shikkhokplus.app.core.network.SalaryLineDto
import com.shikkhokplus.app.core.network.SalaryPaymentBodyDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What payroll and My pay need from the network. */
interface PayrollRepository {
    /**
     * Read one month's salary lines.
     *
     * @param period The month, `yyyy-MM`
     * @return The lines, a refusal, or a transport failure
     */
    suspend fun month(period: String): AuthResult<List<SalaryLineDto>>

    /**
     * Draw the month's lines from the staff records; lines already drawn are kept.
     *
     * @param period The month
     * @return The month's lines, a refusal, or a transport failure
     */
    suspend fun draw(period: String): AuthResult<List<SalaryLineDto>>

    /**
     * Add a bonus or deduction to a draft line.
     *
     * @param lineId The line
     * @param body What and how much
     * @return The line, a refusal, or a transport failure
     */
    suspend fun adjust(lineId: String, body: AdjustmentBodyDto): AuthResult<SalaryLineDto>

    /**
     * Remove a bonus or deduction from a draft line.
     *
     * @param lineId The line
     * @param adjustmentId The adjustment
     * @return The line, a refusal, or a transport failure
     */
    suspend fun removeAdjustment(lineId: String, adjustmentId: String): AuthResult<SalaryLineDto>

    /**
     * Approve a draft line; it can no longer change.
     *
     * @param lineId The line
     * @return The line, a refusal, or a transport failure
     */
    suspend fun approve(lineId: String): AuthResult<SalaryLineDto>

    /**
     * Record a payment against an approved line.
     *
     * @param lineId The line
     * @param body How much, when, and the replay key
     * @return The line, a refusal, or a transport failure
     */
    suspend fun pay(lineId: String, body: SalaryPaymentBodyDto): AuthResult<SalaryLineDto>

    /**
     * Read my own approved salary lines, at every centre.
     *
     * @return The lines, a refusal, or a transport failure
     */
    suspend fun myPay(): AuthResult<List<SalaryLineDto>>
}
