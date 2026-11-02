package com.shikkhokplus.app.feature.fees

import com.shikkhokplus.app.core.network.MonthStateDto
import com.shikkhokplus.app.core.network.toHistoryLine

/**
 * Maps the server's 6-month strip (M3) to rows.
 *
 * An unknown state is an error for the caller, never a default: a
 * month drawn under the wrong glyph looks correct.
 */
object MonthStripMapper {
    /**
     * Convert one strip month, or null when the state is unrecognised.
     *
     * @param month The month the server described
     * @return The row, or null on an unknown state
     */
    fun toRow(month: MonthStateDto): MonthStateRow? {
        val kind =
            when (month.state) {
                "paid" -> StripKind.PAID
                "partly_paid" -> StripKind.PARTIAL
                "unpaid" -> StripKind.UNPAID
                "waived" -> StripKind.WAIVED
                "checking" -> StripKind.CHECKING
                else -> return null
            }
        return MonthStateRow(month.period, kind, month.historyLine?.toHistoryLine())
    }
}
