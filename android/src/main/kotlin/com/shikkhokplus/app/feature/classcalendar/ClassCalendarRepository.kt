package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.network.MonthViewDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the teacher's class calendar needs from the server. */
interface ClassCalendarRepository {
    /**
     * Read one month of one batch.
     *
     * @param batchId The batch
     * @param year The month's year
     * @param month The month, 1 to 12
     * @return The month, a refusal, or a transport failure
     */
    suspend fun month(batchId: String, year: Int, month: Int): AuthResult<MonthViewDto>
}
