package com.shikkhokplus.app.feature.student

import com.shikkhokplus.app.core.network.CurrentFeeDto
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.FamilyBatchViewDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import com.shikkhokplus.app.core.network.StudentBatchDto
import com.shikkhokplus.app.core.network.UpcomingSessionDto
import com.shikkhokplus.app.feature.fees.FeeStateMapper
import com.shikkhokplus.app.feature.marks.MarksStateMapper

/**
 * Maps the student's reads to what S1 and S2 render.
 *
 * Pure, like every mapper here: the decisions are the server's, and
 * this only names them for the screen [TC-9, D-31].
 */
object StudentStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be understood. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /**
     * Map the student's batch list.
     *
     * @param rows What the server returned
     * @param name The student's own name, for S1's subtitle
     * @param phone The student's own number, for the empty state
     * @return The state S1 renders
     */
    fun afterBatches(rows: List<StudentBatchDto>, phone: String?, name: String? = null): MyBatchesUiState {
        if (rows.isEmpty()) return MyBatchesUiState.Empty(phone)
        val batches = rows.map { toRow(it) ?: return MyBatchesUiState.Failed(UNEXPECTED_KEY, false) }
        return MyBatchesUiState.Loaded(batches, name, phone)
    }

    /**
     * Map the three reads behind S2 into one view.
     *
     * @param batch The seat's row from the batch list
     * @param view The batch's classes and notices
     * @param progress The student's own results
     * @return The state S2 renders
     */
    fun afterBatch(
        batch: StudentBatchDto,
        view: FamilyBatchViewDto,
        progress: List<ProgressEntryDto>,
    ): StudentBatchUiState {
        val row = toRow(batch) ?: return StudentBatchUiState.Failed(UNEXPECTED_KEY, false)
        val results =
            MarksStateMapper.progressRows(progress)
                ?: return StudentBatchUiState.Failed(UNEXPECTED_KEY, false)
        return StudentBatchUiState.Loaded(
            StudentBatchView(
                batch = row,
                nextClassDate = view.nextSessionDate,
                nextClassStart = view.nextSessionStartTime?.take(HHMM),
                results = results,
                next = view.nextSession?.let(::toNextClass),
                following = view.followingSessions.map(::toNextClass),
                upcomingExam =
                    view.upcomingExam?.let { UpcomingExam(it.title, it.date, it.totalMarks, it.subjectName) },
                notices = view.announcements.map { NoticeRow(it.body, it.postedAt) },
                // `topicLogged` is the server's: a topic saved blank is
                // logged, and has nothing to show.
                topics =
                    view.pastSessions
                        .filter { it.topicLogged && !it.topic.isNullOrBlank() }
                        .map { TopicRow(it.date, it.topic.orEmpty(), it.subjectName) },
            ),
        )
    }

    /**
     * A seat that is not in the student's own list.
     *
     * @return The failure S2 renders
     */
    fun notFound(): StudentBatchUiState = StudentBatchUiState.Failed("teaching.not_available", false)

    /**
     * Map a server error envelope.
     *
     * @param envelope The server's error
     * @return The key and retry policy the envelope carries
     */
    fun failure(envelope: ErrorEnvelope): Pair<String, Boolean> =
        envelope.error.messageKey to envelope.error.retryable

    /**
     * Convert one seat.
     *
     * @param dto The seat the server returned
     * @return The row, or null for a fee status outside the four
     */
    private fun toRow(dto: StudentBatchDto): StudentBatchRow? {
        val fee = dto.currentFee?.let { toFee(it) ?: return null }
        return StudentBatchRow(
            enrollmentId = dto.enrollmentId,
            batchName = dto.batchName,
            teacherName = dto.teacherDisplayName,
            schedule = dto.schedule,
            fee = fee,
            nextClass = dto.nextSession?.let(::toNextClass),
            isNext = dto.isNext,
            lastResult = dto.lastResult?.let { LastResult(it.title, it.marks, it.totalMarks, it.rank) },
        )
    }

    /**
     * Convert one coming class, trimming the times to `HH:MM`.
     *
     * @param dto The server's class
     * @return The class to show
     */
    private fun toNextClass(dto: UpcomingSessionDto): NextClass =
        NextClass(
            date = dto.date,
            startTime = dto.startTime.take(HHMM),
            endTime = dto.endTime?.take(HHMM),
            startsInMinutes = dto.startsInMinutes,
            moved = dto.moved,
            subjectName = dto.subjectName,
        )

    /**
     * Convert a fee period.
     *
     * @param dto The period the server returned
     * @return The line, or null for a status outside the four
     */
    private fun toFee(dto: CurrentFeeDto): FeeLine? =
        FeeStateMapper.statusKey(dto.status)?.let { key ->
            FeeLine(dto.period, key, dto.dueDate, dto.outstanding, dto.charged, dto.verifying, dto.paidOn)
        }

    /** `HH:MM` out of the server's `HH:MM:SS`. */
    private const val HHMM = 5
}
