package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarRepository
import io.ktor.client.HttpClient
import io.ktor.client.request.get
import io.ktor.client.request.parameter

/**
 * The teacher's class calendar, over HTTP.
 *
 * @property client The authenticated HTTP client
 */
class HttpClassCalendarRepository(
    private val client: HttpClient,
) : ClassCalendarRepository {

    override suspend fun month(batchId: String, year: Int, month: Int): AuthResult<MonthViewDto> =
        call {
            client.get("/v1/batches/$batchId/calendar") {
                parameter("year", year)
                parameter("month", month)
            }
        }
}
