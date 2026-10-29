package com.shikkhokplus.app.feature.dues

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.DuesGroupDto
import com.shikkhokplus.app.core.network.DuesResponseDto
import com.shikkhokplus.app.core.network.DuesRowDto
import com.shikkhokplus.app.core.network.DuesSummaryDto

/**
 * The server's dues headline with three groups, as it always sends
 * them.
 *
 * @param remindable How many seats a reminder would reach
 * @return The summary
 */
internal fun duesSummary(remindable: Int = 0): DuesSummaryDto =
    DuesSummaryDto(
        total = Money.of("6000.00"),
        count = 3,
        lateTotal = Money.of("5100.00"),
        remindable = remindable,
        groups =
            listOf(
                DuesGroupDto("over_30", Money.of("3600.00"), 1, 60),
                DuesGroupDto("late", Money.of("1500.00"), 1, 25),
                DuesGroupDto("not_late", Money.of("900.00"), 1, 15),
            ),
    )

/**
 * One dues row as the server sends it.
 *
 * @param name The teacher-typed name, also the seat id's suffix
 * @param bucket The server's group
 * @param batch The batch id
 * @param reminded When it was last reminded, or null
 * @param remindable Whether a reminder would reach it
 * @return The row
 */
internal fun duesRow(
    name: String,
    bucket: String = "not_late",
    batch: String = "b-1",
    reminded: String? = null,
    remindable: Boolean = false,
): DuesRowDto =
    DuesRowDto(
        enrollmentId = "seat-$name",
        batchId = batch,
        batchName = "Batch $batch",
        displayName = name,
        outstanding = Money.of("1000.00"),
        oldestUnpaidPeriod = "2026-10",
        bucket = bucket,
        daysLate = if (bucket == "not_late") null else 7,
        lastRemindedAt = reminded,
        remindable = remindable,
    )

/**
 * A response holding these rows.
 *
 * @param rows The rows
 * @param remindable The headline's reminder count
 * @return The response
 */
internal fun duesResponse(vararg rows: DuesRowDto, remindable: Int = 0): DuesResponseDto =
    DuesResponseDto(summary = duesSummary(remindable), rows = rows.toList())
