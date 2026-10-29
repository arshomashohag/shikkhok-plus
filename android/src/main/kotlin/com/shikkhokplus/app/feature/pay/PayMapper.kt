package com.shikkhokplus.app.feature.pay

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ClaimDto
import com.shikkhokplus.app.core.network.ClaimSubmitDto
import com.shikkhokplus.app.core.network.PayablesDto
import com.shikkhokplus.app.core.network.PaymentDestinationDto

/**
 * The S3 decisions that are the phone's to make: which screen, and
 * whether what was typed has the shape of a payment. Every amount and
 * every list is the server's.
 */
object PayMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The shortest transaction ID any of the services issues. */
    private const val MIN_TRANSACTION_ID = 6

    /**
     * Map what can be paid: straight to the form when there is one fee
     * and nothing to explain, otherwise the choice.
     *
     * @param dto The server's list
     * @return The options and waiting lines
     */
    fun options(dto: PayablesDto): Pair<List<PayOption>, List<WaitingLine>> =
        dto.payable.map { PayOption(it.enrollmentId, it.batchName, it.period, it.amountDue, it.dueDate) } to
            dto.waiting.map { WaitingLine(it.batchName, it.period) }

    /**
     * The form for one fee, with the amount owed filled in.
     *
     * @param option The fee
     * @param destination Where to pay, or null when the teacher set no number
     * @param canChange Whether other fees were on offer
     * @return The form state
     */
    fun filling(option: PayOption, destination: PaymentDestinationDto?, canChange: Boolean): PayUiState.Filling =
        PayUiState.Filling(
            option = option,
            destination =
                destination?.let { PayDestination(it.collectionNumber, it.collectionChannel, it.teacherDisplayName) },
            channels = destination?.channels.orEmpty().ifEmpty { DEFAULT_CHANNELS },
            form = PayForm(channel = destination?.collectionChannel, amount = option.amountDue.toString()),
            canChange = canChange,
        )

    /**
     * What to send, or the format problem stopping it. Null for both
     * when a field is simply not filled yet.
     *
     * @param form What was typed
     * @return The claim to send, or the problem, or neither
     */
    fun claimOf(form: PayForm): Pair<ClaimSubmitDto?, FormProblem?> {
        val id = form.transactionId.trim()
        val amount = Money.fromTyped(form.amount)
        return when {
            id.isNotEmpty() && id.length < MIN_TRANSACTION_ID -> null to FormProblem.TRANSACTION_ID_SHORT
            form.channel == null || id.isEmpty() || amount == null -> null to null
            else -> ClaimSubmitDto(amount, form.channel, id) to null
        }
    }

    /**
     * The sent payment, from the server's record of it.
     *
     * @param claim The pending claim the server returned
     * @param transactionId The ID that was quoted, which the claim
     *   response does not echo
     * @return What the "Payment sent" screen shows
     */
    fun sent(claim: ClaimDto, transactionId: String): SentPayment =
        SentPayment(claim.claimedAmount, claim.channel, transactionId, claim.submittedAt)

    /** The apps offered if the server named none. */
    private val DEFAULT_CHANNELS = listOf("bKash", "Nagad", "Rocket")
}
