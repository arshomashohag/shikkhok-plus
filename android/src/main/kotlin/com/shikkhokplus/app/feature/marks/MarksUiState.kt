package com.shikkhokplus.app.feature.marks

/**
 * One exam as the teacher's list renders it.
 *
 * @property examId The exam
 * @property title Its title
 * @property dateLabel Its date, as the server formatted it
 * @property subjectName Which subject
 * @property totalMarks Its total
 * @property enteredCount How many seats have a live mark, **counted by
 *   the server** [TC-9]
 * @property expectedCount How many seats could have sat it, which leaves
 *   out a seat that joined after the exam date
 * @property state `upcoming`, `needs_marks` or `complete`, the server's
 *   grouping for T7's Exams tab
 */
data class ExamRow(
    val examId: String,
    val title: String,
    val dateLabel: String,
    val subjectName: String?,
    val totalMarks: Int,
    val enteredCount: Int,
    val expectedCount: Int,
    val state: String = "complete",
)

/**
 * One seat's result as the mark-entry screen renders it [BR4.3].
 *
 * @property enrollmentId The seat
 * @property displayName The teacher-typed name
 * @property stateLabel A string resource key for the result state,
 *   chosen by the mapper from the server's enum
 * @property marks The score, non-null only when the state is `marked`
 *   [BR4.2]. **A zero is a mark**, so null and zero are different here
 *   and nothing collapses them
 * @property isEditable Whether this seat can be marked, **decided
 *   server-side**. A seat that joined after the exam cannot be
 *   [BR4.3], and the client is told rather than comparing dates
 * @property hasHistory Whether anything was ever recorded for the seat,
 *   so its history has something to show
 */
data class MarkRow(
    val enrollmentId: String,
    val displayName: String,
    val stateLabel: String,
    val marks: Int?,
    val isEditable: Boolean,
    val hasHistory: Boolean = false,
)

/**
 * One published band of the distribution [BR6.3].
 *
 * **Already merged by the server**, holding at least three results. The
 * client renders bands and never merges them: a band of one is a named
 * mark, and deciding whether a band is safe to publish is a disclosure
 * rule.
 *
 * @property rangeLabel The band's range, as the mapper formatted it
 * @property count How many results fall in it
 */
data class MarkBand(
    val rangeLabel: String,
    val count: Int,
)

/**
 * The comparison figures, present together or absent together
 * [BR6.4].
 *
 * **One type rather than four nullable fields on the state**, because
 * the four are published as a set: the server withholds all of them
 * below five marked results and withholds them again while any seat is
 * still `not_entered`. Four separate nullables would let a screen
 * render a rank beside a missing average, which is a shape the server
 * never sends and which the client would have had to invent.
 *
 * @property rank The viewer's rank among marked results, or null when
 *   the viewer has no mark to rank (absent, or joined after)
 * @property markedCount What the rank is out of
 * @property average The batch average, formatted for display
 * @property highest The highest marked result
 * @property bands The merged distribution
 */
data class MarksheetComparison(
    val rank: Int?,
    val markedCount: Int,
    val average: String,
    val highest: Int,
    val bands: List<MarkBand>,
)

/** Everything the exam and mark screens render. */
sealed interface MarksUiState {
    /** Nothing has been asked for yet. */
    data object Idle : MarksUiState

    /** A request is in flight. */
    data object Loading : MarksUiState

    /**
     * The exam list loaded.
     *
     * @property batchName Which class
     * @property exams The exams, in the server's order
     */
    data class ExamsLoaded(
        val batchName: String,
        val exams: List<ExamRow>,
    ) : MarksUiState

    /**
     * The batch has no exams yet.
     *
     * @property batchName Which class
     */
    data class ExamsEmpty(val batchName: String) : MarksUiState

    /**
     * One exam's results, open for entry.
     *
     * @property examId The exam
     * @property examTitle Its title
     * @property totalMarks Its total, which bounds every entry [BR4.2]
     * @property rows One row per seat
     * @property writable Whether marks may be written, **decided
     *   server-side** [BR5.5]
     * @property examDate Its date, `yyyy-MM-dd`, for the edit form
     */
    data class EntryLoaded(
        val examId: String,
        val examTitle: String,
        val totalMarks: Int,
        val rows: List<MarkRow>,
        val writable: Boolean,
        val examDate: String = "",
    ) : MarksUiState

    /**
     * The marksheet, as a student or guardian sees it [BR6.2].
     *
     * @property examTitle Which exam
     * @property totalMarks Its total
     * @property ownStateLabel The viewer's own result state
     * @property ownMarks The viewer's own score, if marked
     * @property comparison The aggregates, or **null when the server
     *   published none** [BR6.4].
     *
     *   Null means no rank, no average, no highest and no bands — all
     *   four, together. The client never decides this: a
     *   `markedCount < 5` here would be the client holding the
     *   disclosure rule, and it would be wrong about the second
     *   condition entirely, since the client cannot see whether a seat
     *   is still unmarked
     */
    data class MarksheetLoaded(
        val examTitle: String,
        val totalMarks: Int,
        val ownStateLabel: String,
        val ownMarks: Int?,
        val comparison: MarksheetComparison?,
    ) : MarksUiState

    // **There is deliberately NO `MarksheetHidden` state** [BR5.4].
    //
    // An earlier draft carried one, on the assumption that the server
    // would name the toggle-off case with its own code. It does not,
    // and its choice is the better one: `app/marks/views.py` refuses a
    // family lens whose batch has `marksheet_visible` false through the
    // same shared `refuse()` it uses for a seat the lens cannot reach.
    // So "the toggle is off" and "not your seat" are indistinguishable
    // on the wire, by design -- a family that could tell them apart
    // would learn that a marksheet EXISTS and is merely hidden, which
    // is a fact about the batch they are not entitled to.
    //
    // A state the server can never produce is worse than no state: it
    // reads as working behaviour and nothing fails when it stops being
    // reachable. The toggle-off case renders [Failed] carrying
    // `teaching.not_available`, exactly as an unreachable seat does.

    /**
     * A child's results across exams, in the server's date order
     * [BR6.6].
     *
     * @property childDisplayName Which child
     * @property batchName Which class
     * @property entries The series, oldest first
     */
    data class ProgressLoaded(
        val childDisplayName: String,
        val batchName: String,
        val entries: List<ProgressRow>,
    ) : MarksUiState

    /**
     * Something failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(
        val messageKey: String,
        val retryable: Boolean,
    ) : MarksUiState
}

/**
 * One exam in a child's progress series [BR6.6].
 *
 * @property examId The exam, so a row opens its marksheet
 * @property examTitle Which exam
 * @property dateLabel Its date, as the server formatted it
 * @property totalMarks Its total
 * @property stateLabel A string resource key for the result state
 * @property marks The score, or null.
 *
 *   **Null for an absence, and never zero** [BR6.6]. An absence
 *   plotted as zero shows a collapse in performance that did not
 *   happen, which is the single most alarming thing this screen can say
 *   wrongly. The null is what keeps it out of any trend
 * @property subjectName Which subject, or null
 * @property rank The rank, only where the marksheet publishes it
 * @property rankedOutOf How many marked results the rank is among
 */
data class ProgressRow(
    val examId: String,
    val examTitle: String,
    val dateLabel: String,
    val totalMarks: Int,
    val stateLabel: String,
    val marks: Int?,
    val subjectName: String? = null,
    val rank: Int? = null,
    val rankedOutOf: Int? = null,
)

/**
 * One recorded mark in a seat's history.
 *
 * @property stateLabel Names the recorded result state's string resource
 * @property marks The score, when marked
 * @property recordedAt When it was recorded
 * @property superseded Whether a later correction replaced it
 */
data class HistoryEntry(
    val stateLabel: String,
    val marks: Int?,
    val recordedAt: String,
    val superseded: Boolean,
)

/**
 * A seat's mark history, as the sheet shows it.
 *
 * @property displayName Whose marks
 * @property entries Oldest first, or null while reading
 * @property failed Whether the read failed
 */
data class MarkHistory(
    val displayName: String,
    val entries: List<HistoryEntry>? = null,
    val failed: Boolean = false,
)
