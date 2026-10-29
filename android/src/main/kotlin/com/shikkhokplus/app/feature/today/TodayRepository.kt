package com.shikkhokplus.app.feature.today

import com.shikkhokplus.app.core.network.TodayDto
import com.shikkhokplus.app.feature.auth.AuthResult

/** What the Today screen reads (T1). */
interface TodayRepository {
    /**
     * Read the teacher's day: money owed, classes, payments to check.
     *
     * @return The day's view, a refusal, or a transport failure
     */
    suspend fun today(): AuthResult<TodayDto>
}
