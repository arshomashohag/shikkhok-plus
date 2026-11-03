package com.shikkhokplus.app.feature.dashboard

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.ChildBatchDto
import com.shikkhokplus.app.core.network.ChildSummaryDto
import com.shikkhokplus.app.core.network.DashboardAttendanceMonthDto
import com.shikkhokplus.app.core.network.DashboardDto
import com.shikkhokplus.app.core.network.DashboardExamDto
import com.shikkhokplus.app.core.network.DashboardFeeMonthDto
import com.shikkhokplus.app.core.network.DashboardTilesDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.feature.auth.AuthResult

fun examDto(
    id: String = "x1",
    marks: Int? = 81,
    average: Int? = 72,
    highest: Int? = 95,
) = DashboardExamDto(
    examId = id,
    title = "Ch-5 Motion",
    date = "2026-10-22",
    marks = marks,
    total = 100,
    percent = marks,
    batchAverage = average,
    batchHighest = highest,
)

fun dashboardDto(
    exams: List<DashboardExamDto> = listOf(examDto()),
    examAverage: Int? = 74,
) = DashboardDto(
    tiles =
        DashboardTilesDto(
            attendancePercent = 86,
            present = 43,
            held = 50,
            examAveragePercent = examAverage,
            direction = "up",
            owed = Money.of("2000.00"),
        ),
    attendanceByMonth =
        listOf(
            DashboardAttendanceMonthDto("2026-10", 4, 4, 100, false),
            DashboardAttendanceMonthDto("2026-11", 2, 2, 100, true),
        ),
    exams = exams,
    feeMonths = listOf(DashboardFeeMonthDto("2026-10", "paid"), DashboardFeeMonthDto("2026-11", "unpaid")),
)

fun guardianHome() =
    GuardianHomeDto(
        children =
            listOf(
                ChildSummaryDto(
                    key = "s-1",
                    displayName = "Tanvir",
                    batchCount = 2,
                    batches = listOf(ChildBatchDto("s-1", "Physics"), ChildBatchDto("s-2", "Math")),
                ),
                ChildSummaryDto(
                    key = "s-3",
                    displayName = "Tania",
                    batchCount = 1,
                    batches = listOf(ChildBatchDto("s-3", "Physics")),
                ),
            ),
    )

class FakeDashboardRepository(
    var result: AuthResult<DashboardDto> = AuthResult.Ok(dashboardDto()),
    var respond: (suspend (DashboardRange) -> AuthResult<DashboardDto>)? = null,
    var home: AuthResult<GuardianHomeDto> = AuthResult.Ok(guardianHome()),
) : DashboardRepository {
    val calls = mutableListOf<Triple<DashboardReader, String, DashboardRange>>()

    override suspend fun dashboard(
        reader: DashboardReader,
        seat: String,
        range: DashboardRange,
    ): AuthResult<DashboardDto> {
        calls += Triple(reader, seat, range)
        return respond?.invoke(range) ?: result
    }

    override suspend fun children(): AuthResult<GuardianHomeDto> = home
}

fun dashboardRefusal(
    key: String,
    retryable: Boolean,
) = ErrorEnvelope(ErrorBody(code = "X", messageKey = key, retryable = retryable))
