package com.shikkhokplus.app.feature.guardian

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ChildBatchDto
import com.shikkhokplus.app.core.network.ChildResultDto
import com.shikkhokplus.app.core.network.ChildSummaryDto
import com.shikkhokplus.app.core.network.PayableDto
import com.shikkhokplus.app.core.network.UpcomingSessionDto
import com.shikkhokplus.app.core.network.WaitingPaymentDto

/**
 * One child as the server sends them.
 *
 * @param name The teacher-typed name
 * @param key The child's first seat
 * @return The child
 */
internal fun childDto(name: String, key: String = "seat-$name"): ChildSummaryDto =
    ChildSummaryDto(
        key = key,
        displayName = name,
        batchCount = 2,
        nextPayment =
            PayableDto(key, "Maths", "2026-09", Money.of("1000.00"), "2026-09-10", Money.of("2000.00"), 1, 37),
        waiting =
            listOf(WaitingPaymentDto("Chemistry", "2026-10", Money.of("1200.00"), "Nagad", "2026-10-15T09:00:00Z")),
        latestResults = listOf(ChildResultDto(key, "Physics", "Weekly test 4", "2026-10-12", 44, 50, 39, "up")),
        batches =
            listOf(
                ChildBatchDto(
                    key,
                    "Physics",
                    "Mahfuz",
                    UpcomingSessionDto("2026-10-17", "16:00:00", startsInMinutes = 35),
                ),
            ),
    )
