package com.shikkhokplus.app.feature.pay

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.PaymentSubmitDto
import com.shikkhokplus.app.core.network.StudentBatchDto

/**
 * The decisions that are the phone's to make: how seats group into
 * batches, and whether what was typed has the shape of a payment. Every
 * amount and every owed figure is the server's.
 */
object PayMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The shortest transaction ID any of the services issues. */
    private const val MIN_TRANSACTION_ID = 6

    /**
     * Group the payer's accepted seats by batch, keeping the server's order.
     *
     * @param seats The seats the server listed
     * @return One entry per batch
     */
    fun batches(seats: List<StudentBatchDto>): List<PayBatch> =
        seats
            .groupBy { "${it.batchName}|${it.teacherDisplayName.orEmpty()}" }
            .map { (key, group) ->
                PayBatch(key, group.first().batchName, group.map { PaySeat(it.enrollmentId, it.childName) })
            }

    /**
     * The seats a payment starts out covering.
     *
     * @param batch The chosen batch
     * @param preselect A seat to start on, or null
     * @return That seat when it is in the batch, otherwise every seat
     */
    fun initialSelection(batch: PayBatch, preselect: String?): List<String> =
        batch.seats.map { it.enrollmentId }.let { all ->
            if (preselect != null && preselect in all) listOf(preselect) else all
        }

    /**
     * What to send, or the format problem stopping it. Null for both
     * when a field is simply not filled yet.
     *
     * @param filling The form as it stands
     * @return The payment to send, or the problem, or neither
     */
    fun requestOf(filling: PayUiState.Filling): Pair<PaymentSubmitDto?, FormProblem?> {
        val form = filling.form
        val amount = Money.fromTyped(form.amount)
        val reference = form.transactionId.trim()
        val account = form.fromAccount.trim()
        val choice = filling.choice
        val kind = (choice as? PayChoice.Method)?.method?.kind
        val missing =
            amount == null || form.paidOn.isBlank() || filling.scope.selected.isEmpty() ||
                (kind == "mobile" && reference.isEmpty()) || (kind == "bank" && account.isEmpty())
        return when {
            kind == "mobile" && reference.isNotEmpty() && reference.length < MIN_TRANSACTION_ID ->
                null to FormProblem.TRANSACTION_ID_SHORT
            missing || amount == null -> null to null
            else ->
                PaymentSubmitDto(
                    enrollmentIds = filling.scope.selected,
                    paymentMethodId = (choice as? PayChoice.Method)?.method?.methodId,
                    cash = choice is PayChoice.Cash,
                    amount = amount,
                    paidOn = form.paidOn,
                    transactionId = reference.takeIf { kind == "mobile" },
                    fromAccount = account.takeIf { kind == "bank" },
                    note = form.note.trim().ifEmpty { null },
                ) to null
        }
    }
}
