package com.shikkhokplus.app.feature.dashboard

import com.shikkhokplus.app.core.network.DashboardDto
import com.shikkhokplus.app.core.network.GuardianHomeDto
import com.shikkhokplus.app.feature.auth.AuthResult

/**
 * Who is reading a dashboard. Each reads over its own server path,
 * each resolving its own lens.
 */
enum class DashboardReader {
    /** A teacher reading one of their students. */
    TEACHER,

    /** A student reading their own seat. */
    STUDENT,

    /** A guardian reading a child's seat. */
    GUARDIAN,
}

/**
 * How far back the dashboard reaches.
 *
 * @property wire The value the server's `range` query takes
 */
enum class DashboardRange(val wire: String) {
    /** The last six months. */
    SIX_MONTHS("6m"),

    /** This calendar year. */
    YEAR("year"),

    /** Everything. */
    ALL("all"),
}

/** What the progress dashboard reads from the network. */
interface DashboardRepository {
    /**
     * Read one seat's dashboard.
     *
     * @param reader Who is reading
     * @param seat The seat
     * @param range How far back
     * @return The dashboard, a refusal, or a transport failure
     */
    suspend fun dashboard(
        reader: DashboardReader,
        seat: String,
        range: DashboardRange,
    ): AuthResult<DashboardDto>

    /**
     * Read the guardian's children, for the child switcher and batch picker.
     *
     * @return The children, a refusal, or a transport failure
     */
    suspend fun children(): AuthResult<GuardianHomeDto>
}
