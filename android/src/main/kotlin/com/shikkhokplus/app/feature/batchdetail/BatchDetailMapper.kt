package com.shikkhokplus.app.feature.batchdetail

import com.shikkhokplus.app.core.network.AnnouncementDto
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.RosterFeeRowDto

/**
 * Maps the batch screen's reads (T7). The chip for each student follows
 * the server's own fields in a fixed order and compares no amount [TC-9].
 */
object BatchDetailMapper {
    /**
     * Read the header from the batch.
     *
     * @param dto The batch
     * @return Its header
     */
    fun header(dto: BatchDto): BatchHeader =
        BatchHeader(
            name = dto.name,
            defaultFee = dto.defaultFee,
            feeDueDay = dto.feeDueDay,
            schedule = dto.schedule,
            subjects = dto.subjects,
        )

    /**
     * Choose each seat's fee chip.
     *
     * In order: a payment waiting to be checked; money overdue, with the
     * server's day count; then the current period's own status. A seat
     * whose first period has not generated gets no chip.
     *
     * @param rows The batch's fee rows
     * @return Each seat's chip
     */
    fun chips(rows: List<RosterFeeRowDto>): FeeChips =
        FeeChips.Loaded(rows.mapNotNull { row -> chipFor(row)?.let { row.enrollmentId to it } }.toMap())

    /**
     * Choose one seat's chip.
     *
     * @param row The seat's fee row
     * @return Its chip, or null when there is nothing to show
     */
    fun chipFor(row: RosterFeeRowDto): FeeChip? {
        val verifying = row.verifying
        val days = row.daysOverdue
        return when {
            verifying != null -> FeeChip(FeeChipKind.VERIFYING, amount = verifying)
            days != null -> FeeChip(FeeChipKind.OVERDUE, amount = row.outstanding, days = days)
            row.currentStatus == "partly_paid" -> FeeChip(FeeChipKind.PARTIAL, amount = row.outstanding)
            row.currentStatus == "paid" -> FeeChip(FeeChipKind.PAID)
            row.currentStatus == "waived" -> FeeChip(FeeChipKind.WAIVED)
            row.currentStatus == "unpaid" -> FeeChip(FeeChipKind.DUE, dueDate = row.dueDate)
            else -> null
        }
    }

    /**
     * Convert the notices, keeping the server's order.
     *
     * @param rows The notices
     * @return The notices to show
     */
    fun notices(rows: List<AnnouncementDto>): List<Notice> =
        rows.map { Notice(it.announcementId, it.body, it.postedAt, it.edited) }
}
