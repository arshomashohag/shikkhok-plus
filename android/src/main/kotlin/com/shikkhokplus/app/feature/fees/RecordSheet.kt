package com.shikkhokplus.app.feature.fees

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.RecordPaymentBodyDto

/** How the typed amount stands against what the server says is owed. */
enum class RecordSide {
    /** Not a positive amount yet. */
    INVALID,

    /** The same as what is owed. */
    EXACT,

    /** Less than what is owed: carry or waive must be chosen. */
    SHORT,

    /** More than what is owed: the server holds the rest as credit. */
    OVER,
}

/**
 * "Record payment": money the teacher received by hand for one seat.
 *
 * **Which inputs appear is a display choice** made by comparing the
 * typed amount with the server's [owed]; the server re-checks every
 * choice and is the authority [TC-9]. Nothing here adds, subtracts or
 * divides money: the comparison decides only whether to ask carry or
 * waive, exactly as the approval sheet's does.
 *
 * @property owed What the seat owes now, as the server computed it
 * @property typed The amount received, as typed
 * @property channel `cash`, or one of [MOBILE_SERVICES]
 * @property reference A transaction id or receipt number, if any
 * @property note A note to the family, if any
 * @property disposition `carried` or `waived`, once chosen
 * @property clientMutationId One per opened sheet, reused on a resend
 * @property busy Whether the record is being sent
 * @property errorKey A refused or failed send's message key
 */
data class RecordSheet(
    val owed: Money,
    val typed: String,
    val channel: String = CASH,
    val reference: String = "",
    val note: String = "",
    val disposition: String? = null,
    val clientMutationId: String,
    val busy: Boolean = false,
    val errorKey: String? = null,
) {
    /** The amount typed, or null while it is not a positive amount. */
    val received: Money?
        get() = Money.fromTyped(typed)?.takeIf { it.amount.signum() > 0 }

    /** How the typed amount stands against what is owed. */
    val side: RecordSide
        get() {
            val amount = received ?: return RecordSide.INVALID
            val order = amount.amount.compareTo(owed.amount)
            return when {
                order == 0 -> RecordSide.EXACT
                order < 0 -> RecordSide.SHORT
                else -> RecordSide.OVER
            }
        }

    /** Whether carry or waive must be chosen. */
    val needsDisposition: Boolean get() = side == RecordSide.SHORT

    /** Whether everything the record needs has been supplied. */
    val canConfirm: Boolean
        get() = side != RecordSide.INVALID && (!needsDisposition || disposition != null) && !busy

    /**
     * The request for a confirmed sheet.
     *
     * @return The body, or null while it cannot be sent
     */
    fun body(): RecordPaymentBodyDto? {
        val amount = received ?: return null
        if (!canConfirm) return null
        return RecordPaymentBodyDto(
            amount = amount,
            channel = channel,
            reference = reference.trim().take(REFERENCE_MAX).takeIf { it.isNotEmpty() },
            note = note.trim().take(NOTE_MAX).takeIf { it.isNotEmpty() },
            shortfallDisposition = disposition.takeIf { needsDisposition },
            clientMutationId = clientMutationId,
        )
    }

    companion object {
        /** Money handed over in person: the default channel. */
        const val CASH: String = "cash"

        /**
         * The services a family may send to the teacher's own number.
         * The same three the family route suggests; the server accepts
         * exactly these and cash.
         */
        val MOBILE_SERVICES: List<String> = listOf("bKash", "Nagad", "Rocket")

        /** Cash first, then the mobile services. */
        val CHANNELS: List<String> = listOf(CASH) + MOBILE_SERVICES

        /** The longest note the server stores. */
        const val NOTE_MAX: Int = 500

        /** The longest reference the server stores. */
        const val REFERENCE_MAX: Int = 64

        /**
         * Open the sheet at what the seat owes, in cash.
         *
         * Nothing owed starts blank rather than at ৳0, which the server
         * would refuse.
         *
         * @param owed What the server says the seat owes
         * @param clientMutationId A fresh retry key
         * @return The sheet
         */
        fun open(owed: Money, clientMutationId: String): RecordSheet =
            RecordSheet(
                owed = owed,
                typed =
                    if (owed.amount.signum() == 0) {
                        ""
                    } else {
                        owed.amount.stripTrailingZeros().toPlainString()
                    },
                clientMutationId = clientMutationId,
            )
    }
}
