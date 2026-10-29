package com.shikkhokplus.app.feature.marks

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.ExamDto
import com.shikkhokplus.app.core.network.CorrectionDto
import com.shikkhokplus.app.core.network.ExamResultDto
import com.shikkhokplus.app.core.network.MarkBandDto
import com.shikkhokplus.app.core.network.MarksheetDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import java.util.Locale

/**
 * Maps server responses to a [MarksUiState].
 *
 * **This object is the unit under test**, rather than "the ViewModel".
 * Pure: no network, no storage, no clock.
 *
 * It computes **no aggregate of any kind**. The rank, the average, the
 * highest and the bands all arrive decided [BR6.2–BR6.5], and the
 * reason is sharper than the general client-holds-no-logic rule: every
 * one of them is a **disclosure** decision. A band of one is a named
 * mark; a comparison published below five results identifies people
 * directly; an absence counted as zero drags the average down and moves
 * every rank. The client renders what the server published and tests
 * none of the conditions that produced it.
 */
object MarksStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be parsed. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /** The server's value for a seat that joined after the exam. */
    private const val STATE_JOINED_AFTER: String = "joined_after"

    /**
     * String resource keys for the four result states [BR4.3].
     *
     * **Exhaustive, with an unknown value an error.** Two of these four
     * are derived server-side rather than typed by the teacher, and the
     * cost of a silent fallback is specific: rendering `not_entered` as
     * `absent` publishes an absence the teacher never recorded, on a
     * marksheet the whole batch can see.
     */
    /** The states a teacher recorded, which therefore have a history. */
    private val RECORDED_STATES: Set<String> = setOf("marked", "absent")

    private val RESULT_STATE_KEYS: Map<String, String> =
        mapOf(
            "marked" to "mark.state.marked",
            "absent" to "mark.state.absent",
            "not_entered" to "mark.state.not_entered",
            STATE_JOINED_AFTER to "mark.state.joined_after",
        )

    /**
     * Map a loaded exam list.
     *
     * @param batchName Which class
     * @param exams The exams the server returned, in its order
     * @return The state the screen renders
     */
    fun afterExams(batchName: String, exams: List<ExamDto>): MarksUiState {
        if (exams.isEmpty()) {
            return MarksUiState.ExamsEmpty(batchName)
        }

        return MarksUiState.ExamsLoaded(
            batchName,
            exams.map { dto ->
                ExamRow(
                    examId = dto.examId,
                    title = dto.title,
                    dateLabel = dto.date,
                    subjectName = dto.subjectName,
                    totalMarks = dto.totalMarks,
                    // Carried through, never `rows.count { ... }`.
                    enteredCount = dto.enteredCount,
                    expectedCount = dto.expectedCount,
                    state = dto.state,
                )
            },
        )
    }

    /**
     * Map one exam's results, open for entry.
     *
     * @param examId The exam
     * @param examTitle Its title
     * @param totalMarks Its total
     * @param results One per seat
     * @param writable Whether marks may be written [BR5.5]
     * @return The state the screen renders
     */
    fun afterResults(
        examId: String,
        examTitle: String,
        totalMarks: Int,
        results: List<ExamResultDto>,
        writable: Boolean = true,
        examDate: String = "",
    ): MarksUiState {
        val rows =
            results.map { dto ->
                val label = RESULT_STATE_KEYS[dto.resultState]
                    ?: return MarksUiState.Failed(UNEXPECTED_KEY, retryable = false)

                MarkRow(
                    enrollmentId = dto.enrollmentId,
                    displayName = dto.displayName,
                    stateLabel = label,
                    // Null and zero are different [BR4.2]: a zero is a
                    // mark the student earned, and null is a mark
                    // nobody has entered.
                    marks = dto.marks,
                    // A seat that joined after the exam cannot be
                    // marked at all [BR4.3]. Decided here from the
                    // server's state rather than by comparing dates
                    // the client does not hold.
                    isEditable = writable && dto.resultState != STATE_JOINED_AFTER,
                    hasHistory = dto.resultState in RECORDED_STATES,
                )
            }

        return MarksUiState.EntryLoaded(examId, examTitle, totalMarks, rows, writable, examDate)
    }

    /**
     * Map a seat's mark history, keeping the server's order.
     *
     * A state this app does not know is shown as its own wire value
     * rather than dropped: the history is a record, and a gap in it
     * would misstate what was recorded.
     *
     * @param rows The server's rows, oldest first
     * @return The entries to show
     */
    fun history(rows: List<CorrectionDto>): List<HistoryEntry> =
        rows.map { row ->
            HistoryEntry(
                stateLabel = RESULT_STATE_KEYS[row.resultState] ?: row.resultState,
                marks = row.marks,
                recordedAt = row.recordedAt,
                superseded = row.superseded,
            )
        }

    /**
     * Map a marksheet the server published [BR6.2].
     *
     * **The comparison is present or absent as one unit** [BR6.4]. The
     * server withholds rank, average, highest and bands together, below
     * five marked results and again while any seat is still
     * `not_entered` — two separate conditions, either of which
     * suppresses the set. This reads whether the server published them
     * and never evaluates either condition: the client cannot see
     * whether a seat is unmarked, and testing the count it CAN see
     * would produce a comparison the server deliberately withheld.
     *
     * A partial set from the server is treated as no comparison rather
     * than as a partial one, because a rank beside a missing average is
     * a shape the contract does not define and rendering it would be
     * the client inventing the missing half.
     *
     * @param dto The marksheet
     * @return The state the screen renders
     */
    fun afterMarksheet(dto: MarksheetDto): MarksUiState {
        val ownLabel = RESULT_STATE_KEYS[dto.viewerResultState]
            ?: return MarksUiState.Failed(UNEXPECTED_KEY, retryable = false)

        return MarksUiState.MarksheetLoaded(
            examTitle = dto.examTitle,
            totalMarks = dto.totalMarks,
            ownStateLabel = ownLabel,
            ownMarks = dto.viewerMarks,
            comparison = toComparison(dto),
        )
    }

    /**
     * The comparison the server published, or null when it published
     * none [BR6.4].
     *
     * **[MarksheetDto.published] decides, not the fields.** The
     * server withholds the figures together; a published sheet missing
     * one is a shape the contract does not define, and this returns
     * null for it rather than rendering a count beside a missing
     * average, which would be the client inventing the missing half.
     *
     * The rank alone may be null on a published sheet: a viewer who
     * was absent has no mark to rank, and the batch's figures are
     * still theirs to see.
     *
     * @param dto The marksheet the server returned
     * @return The aggregates, or null when none were published
     */
    private fun toComparison(dto: MarksheetDto): MarksheetComparison? {
        if (!dto.published) return null
        val markedCount = dto.markedCount ?: return null
        val average = dto.average ?: return null
        val highest = dto.highest ?: return null

        return MarksheetComparison(
            rank = dto.viewerRank,
            markedCount = markedCount,
            // Display formatting only, one decimal place in Latin
            // digits per the numeral rule. Nothing is decided from it.
            average = String.format(Locale.ENGLISH, "%.1f", average),
            highest = highest,
            bands = dto.bands.map(::toBand),
        )
    }

    // No `afterMarksheetHidden`: the server does not distinguish the
    // toggle-off case, deliberately. See the note in `MarksUiState`.

    /**
     * Convert one published band.
     *
     * @param dto The band the server published
     * @return The band as the screen renders it
     */
    private fun toBand(dto: MarkBandDto): MarkBand =
        MarkBand(
            // Formatting only. The boundaries and the count are the
            // server's, already merged [BR6.3].
            rangeLabel = "${dto.low}-${dto.high}",
            count = dto.count,
        )

    /**
     * Map a child's progress series [BR6.6].
     *
     * **In the server's order, never sorted here.** Ordering is part of
     * the query; a client sort would differ from the server's tiebreak
     * the moment two exams share a date.
     *
     * @param entries The series
     * @param childDisplayName Whose series, for the heading
     * @param batchName Which class, for the heading
     * @return The state the screen renders
     */
    fun afterProgress(
        entries: List<ProgressEntryDto>,
        childDisplayName: String,
        batchName: String,
    ): MarksUiState {
        val rows = progressRows(entries) ?: return MarksUiState.Failed(UNEXPECTED_KEY, retryable = false)

        return MarksUiState.ProgressLoaded(
            childDisplayName = childDisplayName,
            batchName = batchName,
            entries = rows,
        )
    }

    /**
     * Convert a progress series into rows, in the server's order.
     *
     * Shared by the guardian's progress screen and the student's batch
     * view, so the two cannot render a result state differently.
     *
     * @param entries The series
     * @return The rows, or null when a state is outside the known four
     */
    fun progressRows(entries: List<ProgressEntryDto>): List<ProgressRow>? =
        entries.map { entry ->
            val label = RESULT_STATE_KEYS[entry.resultState] ?: return null
            ProgressRow(
                examId = entry.examId,
                examTitle = entry.title,
                dateLabel = entry.date,
                totalMarks = entry.totalMarks,
                stateLabel = label,
                // **Null for an absence, never zero** [BR6.6]. The
                // temptation is `entry.marks ?: 0` so the renderer
                // has a number for every point; that plots a
                // collapse that did not happen.
                marks = entry.marks,
                subjectName = entry.subjectName,
                rank = entry.rank,
                rankedOutOf = entry.rankedOutOf,
            )
        }

    /**
     * Map a server error envelope.
     *
     * @param envelope The server's error
     * @return The failure state
     */
    fun afterError(envelope: ErrorEnvelope): MarksUiState =
        MarksUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): MarksUiState =
        MarksUiState.Failed(OFFLINE_KEY, retryable = true)
}
