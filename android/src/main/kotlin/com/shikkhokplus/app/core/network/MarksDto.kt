package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One exam as the teacher's list shows it [BR4.1].
 *
 * `totalMarks` is an `Int` and not a [com.shikkhokplus.app.core.model.Money]:
 * a mark out of 100 is a count, not an amount, and the money type would
 * be wrong in both directions — it would admit a decimal where the rule
 * says integer [BR4.2], and it would attract the money formatter where
 * `Numerals.marks` is the right one.
 *
 * @property examId The exam
 * @property title The teacher's name for it
 * @property date The exam date, as the server formatted it
 * @property subjectName Which subject
 * @property totalMarks The exam's total, at least one [BR4.1]
 * @property enteredCount How many seats have a live mark, counted
 *   server-side. **Never a tally over a rows list here** — the client
 *   counting is the client deciding what counts as entered, and it is
 *   wrong the moment the list paginates
 * @property expectedCount How many seats could have sat it, which leaves
 *   out a seat that joined after the exam date
 * @property state `upcoming`, `needs_marks` or `complete`, decided by the
 *   server so the client never compares a date or a count
 */
@Serializable
data class ExamDto(
    @SerialName("exam_id") val examId: String,
    val title: String,
    val date: String,
    @SerialName("subject_name") val subjectName: String? = null,
    @SerialName("total_marks") val totalMarks: Int,
    @SerialName("entered_count") val enteredCount: Int = 0,
    @SerialName("expected_count") val expectedCount: Int = 0,
    val state: String = "complete",
)

/**
 * One seat's result for one exam [BR4.3].
 *
 * **`resultState` arrives decided, and two of its four values are
 * derived rather than typed by the teacher.** A seat with no live mark
 * is `joined_after` when the enrollment joined after the exam date and
 * `not_entered` otherwise — facts about the data, which the client
 * cannot recompute because it holds neither `joined_on` nor the exam
 * date in a comparable form, and must not recompute even if it did.
 *
 * Conflating `not_entered` with `absent` publishes an absence the
 * teacher never recorded, on a shared marksheet [BR4.3]; a client-side
 * `marks == null ? "absent"` is exactly that conflation.
 *
 * @property enrollmentId The seat
 * @property displayName The teacher-typed name
 * @property resultState `marked`, `absent`, `not_entered` or
 *   `joined_after`
 * @property marks The score, non-null **only** when `resultState` is
 *   `marked` [BR4.2]. A zero is a mark and is never absence
 */
@Serializable
data class ExamResultDto(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("result_state") val resultState: String,
    val marks: Int? = null,
)

/**
 * The body of a mark write [BR3.11, BR4.2].
 *
 * **No version and no mutation id**, deliberately. Mark entry is an
 * interactive write, so it cannot conflict: last-write-wins per field,
 * with the actor and time recorded in the correction history. Stating
 * that here is what stops the queued-path rule spreading to every write
 * in the unit — applied everywhere, optimistic concurrency would make a
 * teacher correcting a mark on their own phone refetch for no reason.
 *
 * @property enrollmentId The seat being marked
 * @property resultState `marked` or `absent`. The two derived states
 *   are never written
 * @property marks The score, required for `marked` and null otherwise
 */
@Serializable
data class MarkWriteBody(
    @SerialName("enrollment_id") val enrollmentId: String,
    @SerialName("result_state") val resultState: String,
    val marks: Int? = null,
)

/**
 * One published band of the distribution [BR6.3].
 *
 * **Every published band holds at least three results.** The merging
 * happens on the server, repeating until no band is under three — a
 * band of one IS a named mark, with the name supplied by anyone who
 * knows who is in the batch. The client receives bands already merged
 * and renders them; it never merges, and never decides whether a band
 * is safe to show.
 *
 * @property low The band's lowest mark, inclusive
 * @property high The band's highest mark, inclusive
 * @property count How many results fall in it, always three or more
 */
@Serializable
data class MarkBandDto(
    val low: Int,
    val high: Int,
    val count: Int,
)

/**
 * What a student or guardian sees for one exam [BR6.2].
 *
 * **Never a list of other students' marks.** In a batch of 8 to 20
 * students who sit together and compare marks, twelve unattributed
 * numbers are deanonymised by inference within a day, so a row list
 * would over-claim "anonymised" for a product under a Families
 * declaration. What arrives is the viewer's own mark named, plus
 * aggregates.
 *
 * **One class for the server's two shapes**, discriminated by
 * [published]. A published marksheet carries the comparison; a
 * suppressed one carries only the viewer's own result and [reason].
 * The server withholds the comparison below five marked results and
 * again while any seat is still `not_entered` [BR6.4]; the client
 * reads [published] and tests neither condition.
 *
 * @property published Whether a comparison was published
 * @property examTitle The exam's title
 * @property totalMarks Its total
 * @property viewerResultState The viewer's own result state [BR4.3]
 * @property viewerMarks The viewer's own score, if marked
 * @property viewerRank Their rank among marked results; null when
 *   nothing was published, or when the viewer was not marked
 * @property markedCount How many results the rank is out of
 * @property average The mean of marked results. A marks average, not
 *   money, so a `Double` is the right type; the screen formats it and
 *   decides nothing from it
 * @property highest The highest marked result
 * @property bands The merged distribution [BR6.3]
 * @property reason Why nothing was published, on the suppressed shape
 */
@Serializable
data class MarksheetDto(
    val published: Boolean,
    @SerialName("exam_title") val examTitle: String,
    @SerialName("total_marks") val totalMarks: Int,
    @SerialName("viewer_result_state") val viewerResultState: String,
    @SerialName("viewer_marks") val viewerMarks: Int? = null,
    @SerialName("viewer_rank") val viewerRank: Int? = null,
    @SerialName("marked_count") val markedCount: Int? = null,
    val average: Double? = null,
    val highest: Int? = null,
    val bands: List<MarkBandDto> = emptyList(),
    val reason: String? = null,
)

/**
 * One exam in a child's progress series [BR6.6].
 *
 * **Ordered by exam date in the server's query**, never sorted here. A
 * client sort is a client deciding the series' shape, and it would be
 * wrong the moment two exams share a date and the server's tiebreak
 * differs from the client's.
 *
 * **An absence carries no value** and is not a zero. An absence plotted
 * as zero shows a collapse in performance that did not happen, which is
 * the single most alarming thing this screen can say wrongly.
 *
 * @property examId The exam
 * @property title Its title
 * @property date Its date, as the server formatted it
 * @property totalMarks Its total
 * @property resultState `marked`, `absent`, `not_entered` or
 *   `joined_after`
 * @property marks The score, non-null only when `marked`
 * @property subjectName Which subject the exam was in
 * @property rank The rank, only where the marksheet publishes it
 * @property rankedOutOf How many marked results the rank is among
 * @property batchAverage The batch's average mark, where published; a
 *   count of marks, never money, so a Double is right here
 */
@Serializable
data class ProgressEntryDto(
    @SerialName("exam_id") val examId: String,
    val title: String,
    val date: String,
    @SerialName("total_marks") val totalMarks: Int,
    @SerialName("result_state") val resultState: String,
    val marks: Int? = null,
    @SerialName("subject_name") val subjectName: String? = null,
    val rank: Int? = null,
    @SerialName("ranked_out_of") val rankedOutOf: Int? = null,
    @SerialName("batch_average") val batchAverage: Double? = null,
)

/**
 * One exam's results, as the wire carries them [BR4.3, BR5.5].
 *
 * **A wrapper rather than a bare array, and `writable` is why.** An
 * exam in an inactive batch is read-only, and that is a server
 * decision — without the flag the screen either guesses or offers an
 * entry field whose save is refused, which is the failure a person
 * blames on the app.
 *
 * @property exam The exam, so the screen can show its title and total
 *   without a second call
 * @property results One row per seat, in the server's order
 * @property writable Whether marks may be written
 */
@Serializable
data class ExamResultsResponseDto(
    val exam: ExamDto,
    val results: List<ExamResultDto> = emptyList(),
    val writable: Boolean,
)

/**
 * The body of an exam creation [BR4.1].
 *
 * @property title The teacher's name for the exam
 * @property date The exam date
 * @property totalMarks The total, at least one
 * @property batchSubjectId Which of the batch's subjects. The
 *   belongs-to-batch check is the server's
 */
@Serializable
data class ExamCreateRequestDto(
    val title: String,
    val date: String,
    @SerialName("total_marks") val totalMarks: Int,
    @SerialName("batch_subject_id") val batchSubjectId: String,
)

/**
 * The body of an exam edit. No subject: the exam stays in the subject
 * it was set in.
 *
 * @property title The new title
 * @property date The new date
 * @property totalMarks The new total; the server refuses one below a
 *   mark already recorded
 */
@Serializable
data class ExamUpdateRequestDto(
    val title: String,
    val date: String,
    @SerialName("total_marks") val totalMarks: Int,
)

/**
 * One row of a seat's mark history, oldest first [FR9.2].
 *
 * @property markId The row
 * @property resultState `marked` or `absent`, as recorded
 * @property marks The score, when marked
 * @property recordedAt When it was recorded
 * @property superseded Whether a later correction replaced it
 */
@Serializable
data class CorrectionDto(
    @SerialName("mark_id") val markId: String,
    @SerialName("result_state") val resultState: String,
    val marks: Int? = null,
    @SerialName("recorded_at") val recordedAt: String,
    val superseded: Boolean,
)

/**
 * The body of a marksheet visibility toggle [BR5.4].
 *
 * @property visible Whether families see marksheets for this batch
 */
@Serializable
data class MarksheetToggleRequestDto(
    val visible: Boolean,
)
