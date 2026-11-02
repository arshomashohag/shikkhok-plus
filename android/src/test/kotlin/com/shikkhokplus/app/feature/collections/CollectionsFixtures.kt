package com.shikkhokplus.app.feature.collections

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.BatchFeesDto
import com.shikkhokplus.app.core.network.CollectionsDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.HistoryLineDto
import com.shikkhokplus.app.core.network.MonthCollectionDto
import com.shikkhokplus.app.core.network.MonthCountsDto
import com.shikkhokplus.app.core.network.RosterFeeRowDto
import com.shikkhokplus.app.feature.auth.AuthResult

fun refusal(
    key: String,
    retryable: Boolean,
) = ErrorEnvelope(ErrorBody(code = "X", messageKey = key, retryable = retryable))

fun batchDto(
    id: String,
    name: String,
) = BatchDto(id = id, name = name)

fun monthDto(
    period: String,
    inProgress: Boolean = false,
    chargedBar: Int = 100,
    collectedBar: Int = 60,
) = MonthCollectionDto(
    period = period,
    charged = Money.of("1000.00"),
    collected = Money.of("600.00"),
    inProgress = inProgress,
    chargedBar = chargedBar,
    collectedBar = collectedBar,
)

fun seatDto(
    id: String,
    state: String?,
    days: Int? = null,
    line: HistoryLineDto? = null,
) = RosterFeeRowDto(
    enrollmentId = id,
    displayName = "Seat $id",
    outstanding = Money.of("100.00"),
    daysOverdue = days,
    state = state,
    historyLine = line,
)

fun monthFees(
    period: String,
    seats: List<RosterFeeRowDto> = emptyList(),
    paid: Int = 0,
    checking: Int = 0,
    owed: Int = 0,
) = BatchFeesDto(
    period = period,
    collected = Money.of("900.00"),
    charged = Money.of("1200.00"),
    counts = MonthCountsDto(paid = paid, checking = checking, owed = owed),
    seats = seats,
)

class FakeCollectionsRepository(
    var batches: AuthResult<List<BatchDto>> =
        AuthResult.Ok(listOf(batchDto("b-1", "Physics"), batchDto("b-2", "Math"))),
    var report: AuthResult<CollectionsDto> =
        AuthResult.Ok(
            CollectionsDto(
                months = listOf(monthDto("2026-10"), monthDto("2026-11", inProgress = true)),
                outstanding = Money.of("9500.00"),
                owingStudents = 11,
            ),
        ),
    var month: (String, String?) -> AuthResult<BatchFeesDto> = { _, period ->
        AuthResult.Ok(monthFees(period ?: "2026-11"))
    },
) : CollectionsRepository {
    val reportCalls = mutableListOf<List<String>>()
    val monthCalls = mutableListOf<Pair<String, String?>>()

    override suspend fun batches() = batches

    override suspend fun collections(
        batchIds: List<String>,
        months: Int,
    ): AuthResult<CollectionsDto> {
        reportCalls += batchIds
        return report
    }

    override suspend fun batchMonth(
        batchId: String,
        period: String?,
    ): AuthResult<BatchFeesDto> {
        monthCalls += batchId to period
        return month(batchId, period)
    }
}
