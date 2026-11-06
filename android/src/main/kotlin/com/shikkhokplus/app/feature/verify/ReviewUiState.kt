package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.network.ExtraFeeRefDto
import com.shikkhokplus.app.core.model.Money

/** How the amount in the approval sheet stands against what is owed. */
enum class AmountSide {
    /** Not an amount yet. */
    INVALID,

    /** The same as what the children owe together. */
    EXACT,

    /** Less than what they owe together. */
    SHORT,

    /** More than what they owe together. */
    OVER,
}

/**
 * The approval sheet (R4): what was received, and how to split it.
 *
 * **Which inputs appear is a display choice** made by comparing the
 * typed amount with the server's `owed_together`; the server re-checks
 * every choice and is the authority [TC-9]. Nothing here divides money.
 *
 * @property card The payment being approved
 * @property typed The amount received, as typed
 * @property disposition `carried` or `waived`, once chosen
 * @property childId The child who carries a shortfall or gets a credit
 * @property note A note to the family, if any
 */
data class ApprovalSheet(
    val card: ReviewCard,
    val typed: String,
    val disposition: String? = null,
    val childId: String? = null,
    val note: String = "",
) {
    /** The amount typed, or null while it is not a valid amount. */
    val received: Money? get() = Money.fromTyped(typed)

    /** How the typed amount stands against what is owed together. */
    val side: AmountSide
        get() {
            val amount = received ?: return AmountSide.INVALID
            val order = amount.amount.compareTo(card.owedTogether.amount)
            return when {
                order == 0 -> AmountSide.EXACT
                order < 0 -> AmountSide.SHORT
                else -> AmountSide.OVER
            }
        }

    /** Whether carry or waive must be chosen. */
    val needsDisposition: Boolean get() = side == AmountSide.SHORT

    /** Whether a child must be named, which only several children need. */
    val needsChild: Boolean
        get() = card.children.size > 1 && (side == AmountSide.SHORT || side == AmountSide.OVER)

    /**
     * The server's difference, shown only while the amount is the one the
     * payer reported, since the client never subtracts.
     */
    val shownDifference: Money?
        get() = card.difference.takeIf { received == card.totalAmount }

    /** Whether everything the sheet needs has been supplied. */
    val canConfirm: Boolean
        get() =
            side != AmountSide.INVALID &&
                (!needsDisposition || disposition != null) &&
                (!needsChild || childId != null)
}

/**
 * What a payment is for, as the server reports it.
 *
 * Null means the monthly fee throughout. While the teacher previews
 * another purpose, [applied] is the previewed one: the server measured
 * the payment against it.
 *
 * @property applied The fee it is applied to, or null for monthly
 * @property requested The fee the family chose, or null for monthly
 * @property options The fees the teacher may apply it to instead
 */
data class PaymentPurposeView(
    val applied: ExtraFeeRefDto? = null,
    val requested: ExtraFeeRefDto? = null,
    val options: List<ExtraFeeRefDto> = emptyList(),
) {
    /** Every fee the choice lists: the options, and the applied and chosen ones. */
    val fees: List<ExtraFeeRefDto>
        get() = (options + listOfNotNull(requested, applied)).distinctBy { it.extraFeeId }

    /** Whether there is anything to choose between, or to say. */
    val shown: Boolean get() = fees.isNotEmpty()

    /** Whether it is applied to something other than what the family chose. */
    val changed: Boolean get() = applied?.extraFeeId != requested?.extraFeeId
}

/** Everything R2 and R3 render. */
sealed interface ReviewUiState {
    /** The payment is loading. */
    data object Loading : ReviewUiState

    /**
     * The payment, pending or decided.
     *
     * @property card The payment
     * @property busy Whether a decision is being sent
     * @property errorKey A refused or failed write's message key
     * @property correcting True once the teacher chose to change a decision
     * @property purpose What the payment is for
     * @property preview `monthly` or a fee id while the teacher tries
     *   another purpose; null while it reads as stored
     */
    data class Loaded(
        val card: ReviewCard,
        val busy: Boolean = false,
        val errorKey: String? = null,
        val correcting: Boolean = false,
        val purpose: PaymentPurposeView = PaymentPurposeView(),
        val preview: String? = null,
    ) : ReviewUiState {
        /** Whether Approve and Reject are offered. */
        val canDecide: Boolean get() = card.status == ReviewStatus.PENDING || correcting
    }

    /**
     * The payment could not be read.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : ReviewUiState
}
