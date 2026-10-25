package com.shikkhokplus.app.feature.overview

import com.shikkhokplus.app.core.model.Money

/**
 * One month of the earnings series.
 *
 * @property period The month as `YYYY-MM`
 * @property received What arrived that month
 */
data class EarningsPoint(
    val period: String,
    val received: Money,
)

/**
 * The next exam block, when there is one.
 *
 * `daysRemaining` is **carried from the server**, never derived from
 * [date]: a client computing it would use the device clock, which this
 * product rules out for decisions, and would disagree across time
 * zones.
 *
 * @property title The teacher's name for the exam
 * @property batchName Which class sits it
 * @property subjectName The subject assessed
 * @property date When it is sat, as the server sent it
 * @property daysRemaining Whole days, computed server-side
 */
data class NextExam(
    val title: String,
    val batchName: String,
    val subjectName: String,
    val date: String,
    val daysRemaining: Int,
)

/**
 * Everything the teacher overview renders.
 *
 * **[Loaded] carries three blocks with different absence rules**, and
 * the type encodes the difference rather than leaving it to the screen:
 * `thisMonth` is non-null because zero is a value, while `trend` and
 * `nextExam` are nullable because absent and zero are different things.
 *
 * There is no `Empty` state here, deliberately. An overview always has
 * something to say — at minimum this month's earnings, which is a
 * figure even when it is zero — so an empty state would be a screen
 * that cannot be reached.
 */
sealed interface OverviewUiState {
    /** Nothing has been asked for yet. */
    data object Idle : OverviewUiState

    /** A request is in flight. */
    data object Loading : OverviewUiState

    /**
     * The overview loaded.
     *
     * @property thisMonth This month's earnings. **Never null**: a
     *   month with no receipts carries a zero VALUE, because zero
     *   earned is a fact about the month and rendering it as "no data"
     *   would tell a teacher their records are missing when they are
     *   complete
     * @property trend The monthly series ascending, or **null under two
     *   months of history**. Null rather than an empty list, so the
     *   screen omits the block entirely rather than drawing an empty
     *   chart frame: a single point implies a direction it cannot know
     * @property nextExam The soonest upcoming exam, or null when
     *   nothing is scheduled — which the screen renders as a defined
     *   empty state rather than a failure
     */
    data class Loaded(
        val thisMonth: EarningsPoint,
        val trend: List<EarningsPoint>?,
        val nextExam: NextExam?,
    ) : OverviewUiState

    /**
     * Something failed.
     *
     * @property messageKey Names a string resource; never English text
     *   from the server [TC-15, D-43]
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : OverviewUiState
}
