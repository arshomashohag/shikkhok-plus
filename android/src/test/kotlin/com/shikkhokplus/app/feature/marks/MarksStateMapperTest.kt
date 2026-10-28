package com.shikkhokplus.app.feature.marks

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.ExamDto
import com.shikkhokplus.app.core.network.CorrectionDto
import com.shikkhokplus.app.core.network.ExamResultDto
import com.shikkhokplus.app.core.network.MarkBandDto
import com.shikkhokplus.app.core.network.MarksheetDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The exam, mark and marksheet mapping decisions.
 *
 * Every aggregate on the marksheet is a **disclosure** decision rather
 * than a formatting one [BR6.2–BR6.5], so the assertions here are
 * mostly about what the client does NOT compute: it never decides
 * whether a comparison may be published, never merges a band, and never
 * turns an absence into a zero.
 */
class MarksStateMapperTest {

    private fun exam(examId: String = "x-1", entered: Int = 0, seats: Int = 8): ExamDto =
        ExamDto(
            examId = examId,
            title = "Mid-term",
            date = "12 May",
            totalMarks = 100,
            enteredCount = entered,
            expectedCount = seats,
        )

    private fun result(
        enrollmentId: String = "e-1",
        state: String = "marked",
        marks: Int? = 55,
    ): ExamResultDto =
        ExamResultDto(
            enrollmentId = enrollmentId,
            displayName = "Rahim",
            resultState = state,
            marks = marks,
        )

    private fun marksheet(
        ownState: String = "marked",
        ownMarks: Int? = 74,
        published: Boolean = false,
        rank: Int? = null,
        markedCount: Int? = null,
        average: Double? = null,
        highest: Int? = null,
        bands: List<MarkBandDto> = emptyList(),
    ): MarksheetDto =
        MarksheetDto(
            published = published,
            examTitle = "Mid-term",
            totalMarks = 100,
            viewerResultState = ownState,
            viewerMarks = ownMarks,
            viewerRank = rank,
            markedCount = markedCount,
            average = average,
            highest = highest,
            bands = bands,
            reason = if (published) null else "too_few_results",
        )

    // ------------------------------------------------------------------
    // The four result states [BR4.3].
    // ------------------------------------------------------------------

    @Test
    fun `each of the four result states maps to its own key`() {
        // **Two of the four are DERIVED server-side**, not typed by
        // the teacher, and conflating `not_entered` with `absent`
        // publishes an absence nobody recorded on a shared marksheet.
        val labels =
            listOf("marked", "absent", "not_entered", "joined_after").map { state ->
                val loaded =
                    assertIs<MarksUiState.EntryLoaded>(
                        MarksStateMapper.afterResults(
                            "x-1",
                            "Mid-term",
                            100,
                            listOf(result(state = state, marks = null)),
                        ),
                    )
                loaded.rows.single().stateLabel
            }

        assertEquals(
            listOf(
                "mark.state.marked",
                "mark.state.absent",
                "mark.state.not_entered",
                "mark.state.joined_after",
            ),
            labels,
        )
        assertEquals(4, labels.distinct().size)
    }

    @Test
    fun `an unknown result state fails loudly rather than defaulting`() {
        val state =
            MarksStateMapper.afterResults(
                "x-1",
                "Mid-term",
                100,
                listOf(result(state = "withdrawn")),
            )

        assertEquals(
            MarksStateMapper.UNEXPECTED_KEY,
            assertIs<MarksUiState.Failed>(state).messageKey,
        )
    }

    @Test
    fun `a zero is a mark and is not an absence`() {
        // THE RULE [BR4.2]. A zero stored as absent tells a guardian
        // their child missed an exam they sat and failed; the reverse
        // says they scored nothing when they were ill.
        val row =
            assertIs<MarksUiState.EntryLoaded>(
                MarksStateMapper.afterResults(
                    "x-1",
                    "Mid-term",
                    100,
                    listOf(result(state = "marked", marks = 0)),
                ),
            ).rows.single()

        assertEquals(0, row.marks)
        assertEquals("mark.state.marked", row.stateLabel)
        assertNotEquals("mark.state.absent", row.stateLabel)
    }

    @Test
    fun `a seat that joined after the exam cannot be marked`() {
        // BR4.3. Decided from the server's state, never by comparing
        // dates the client does not hold.
        val rows =
            assertIs<MarksUiState.EntryLoaded>(
                MarksStateMapper.afterResults(
                    "x-1",
                    "Mid-term",
                    100,
                    listOf(
                        result("e-1", "not_entered", null),
                        result("e-2", "joined_after", null),
                    ),
                ),
            ).rows

        assertEquals(true, rows[0].isEditable)
        assertEquals(false, rows[1].isEditable)
    }

    @Test
    fun `nothing is editable when the server says the exam is read-only`() {
        // BR5.5: an inactive batch is read-only and no write succeeds
        // against it.
        val rows =
            assertIs<MarksUiState.EntryLoaded>(
                MarksStateMapper.afterResults(
                    "x-1",
                    "Mid-term",
                    100,
                    listOf(result(state = "not_entered", marks = null)),
                    writable = false,
                ),
            ).rows

        assertEquals(false, rows.single().isEditable)
    }

    // ------------------------------------------------------------------
    // The marksheet thresholds [BR6.4] -- two conditions, one result.
    // ------------------------------------------------------------------

    @Test
    fun `no comparison is published when the server published none`() {
        // THE RULE [BR6.4]. The server withholds all four figures
        // below five marked results, and again while any seat is still
        // unmarked. The client evaluates NEITHER condition -- it
        // cannot see the second at all, and testing the first would
        // publish a comparison the server deliberately withheld.
        val loaded =
            assertIs<MarksUiState.MarksheetLoaded>(
                MarksStateMapper.afterMarksheet(marksheet()),
            )

        assertNull(loaded.comparison)
        assertEquals(74, loaded.ownMarks)
    }

    @Test
    fun `the comparison is carried through whole when the server published it`() {
        // The worked case from security-design § 4.2, which the server
        // computed: nine marked results, three published bands of
        // three, average 64.67, highest 92, the 74 ranking 4th.
        val loaded =
            assertIs<MarksUiState.MarksheetLoaded>(
                MarksStateMapper.afterMarksheet(
                    marksheet(
                        published = true,
                        rank = 4,
                        markedCount = 9,
                        average = 64.666_666,
                        highest = 92,
                        bands =
                            listOf(
                                MarkBandDto(80, 100, 3),
                                MarkBandDto(60, 79, 3),
                                MarkBandDto(0, 59, 3),
                            ),
                    ),
                ),
            )

        val comparison = requireNotNull(loaded.comparison)
        assertEquals(4, comparison.rank)
        assertEquals(9, comparison.markedCount)
        // One decimal place, Latin digits: display formatting only.
        assertEquals("64.7", comparison.average)
        assertEquals(92, comparison.highest)
        assertEquals(
            listOf("80-100", "60-79", "0-59"),
            comparison.bands.map { it.rangeLabel },
        )
        assertEquals(listOf(3, 3, 3), comparison.bands.map { it.count })
    }

    @Test
    fun `bands are rendered as published, never re-merged by the client`() {
        // THE RULE [BR6.3]: a band of one IS a named mark. The merging
        // is the server's and repeats until every published band holds
        // at least three; a client that merged again would produce a
        // different distribution from the one the server published.
        val loaded =
            assertIs<MarksUiState.MarksheetLoaded>(
                MarksStateMapper.afterMarksheet(
                    marksheet(
                        published = true,
                        rank = 1,
                        markedCount = 6,
                        average = 70.0,
                        highest = 90,
                        bands = listOf(MarkBandDto(60, 100, 3), MarkBandDto(0, 59, 3)),
                    ),
                ),
            )

        assertEquals(2, requireNotNull(loaded.comparison).bands.size)
        assertTrue(loaded.comparison.bands.all { it.count >= 3 })
    }

    @Test
    fun `a partial comparison from the server is treated as none`() {
        // A rank beside a missing average is a shape the contract does
        // not define, and rendering it would be the client inventing
        // the missing half.
        val loaded =
            assertIs<MarksUiState.MarksheetLoaded>(
                MarksStateMapper.afterMarksheet(
                    marksheet(
                        published = true,
                        rank = 4,
                        markedCount = 9,
                        average = null,
                        highest = 92,
                    ),
                ),
            )

        assertNull(loaded.comparison)
    }

    @Test
    fun `an absent viewer still sees the batch's published figures, without a rank`() {
        // The server publishes the comparison with no rank for a viewer
        // who has no mark to rank. Dropping the whole comparison for a
        // null rank would hide figures the viewer is entitled to.
        val loaded =
            assertIs<MarksUiState.MarksheetLoaded>(
                MarksStateMapper.afterMarksheet(
                    marksheet(
                        ownState = "absent",
                        ownMarks = null,
                        published = true,
                        rank = null,
                        markedCount = 6,
                        average = 70.0,
                        highest = 90,
                    ),
                ),
            )

        val comparison = requireNotNull(loaded.comparison)
        assertNull(comparison.rank)
        assertEquals("mark.state.absent", loaded.ownStateLabel)
    }

    @Test
    fun `the toggle being off returns no marksheet at all`() {
        // THE RULE [BR5.4]. Not an empty marksheet -- an empty one
        // still discloses that exams exist and how many.
        //
        // **The toggle-off case arrives as the SHARED refusal**, not
        // as a state of its own: `app/marks/views.py` refuses a family
        // lens whose batch has `marksheet_visible` false through the
        // same `refuse()` it uses for a seat the lens cannot reach. An
        // earlier draft of this test called an
        // `afterMarksheetHidden()` that mapped a
        // `MARKSHEET_NOT_PUBLISHED` code the backend never emits, so
        // it asserted a path no server response could reach.
        val state =
            MarksStateMapper.afterError(
                ErrorEnvelope(
                    ErrorBody(
                        code = "NOT_AVAILABLE",
                        retryable = false,
                        messageKey = "teaching.not_available",
                    ),
                ),
            )

        // **Asserted as THREE absences, each separately**, because
        // "not a loaded marksheet" alone would pass against a loaded
        // one carrying empty fields -- and an empty marksheet still
        // discloses that exams exist and how many, which is precisely
        // what the toggle exists to prevent.
        assertFalse(state is MarksUiState.MarksheetLoaded, "no marksheet object")
        assertFalse(state is MarksUiState.ExamsLoaded, "no exam list")
        assertFalse(state is MarksUiState.ExamsEmpty, "no exam count, not even zero")

        val failed = assertIs<MarksUiState.Failed>(state)
        // The shared key, which reads the same for an unreachable seat
        // -- that identity IS the control [security-design § 2.3].
        assertEquals("teaching.not_available", failed.messageKey)
        assertEquals(false, failed.retryable)
    }

    @Test
    fun `a hidden marksheet and an unreachable seat render identically`() {
        // **The oracle property, asserted on the client side**
        // [BR3.10, security-design § 2.3]. The server returns the same
        // code and key for "the toggle is off" and "that seat is not
        // yours", so a family cannot learn that a marksheet exists and
        // is merely hidden.
        //
        // The client can still break that: a `when` on the code that
        // rendered one of them differently would reintroduce the
        // oracle in the UI after the server closed it. Asserting
        // EQUALITY of the two mapped states is what catches that --
        // two independent "is a failure" assertions would both pass
        // while the rendered states differed.
        val envelope =
            ErrorEnvelope(
                ErrorBody(
                    code = "NOT_AVAILABLE",
                    retryable = false,
                    messageKey = "teaching.not_available",
                ),
            )

        assertEquals(
            MarksStateMapper.afterError(envelope),
            MarksStateMapper.afterError(envelope),
        )
        // And neither is special-cased into a distinct state.
        assertIs<MarksUiState.Failed>(MarksStateMapper.afterError(envelope))
    }

    // ------------------------------------------------------------------
    // Guardian progress [BR6.6].
    // ------------------------------------------------------------------

    @Test
    fun `an absence carries no value and is not a zero`() {
        // **THE RULE** [BR6.6]. An absence plotted as zero shows a
        // collapse in performance that did not happen, which is the
        // single most alarming thing this screen can say wrongly. The
        // temptation is `marks ?: 0` so every point has a number.
        val loaded =
            assertIs<MarksUiState.ProgressLoaded>(
                MarksStateMapper.afterProgress(
                    listOf(
                        ProgressEntryDto("x-1", "First", "01 Mar", 100, "marked", 70),
                        ProgressEntryDto("x-2", "Second", "01 Apr", 100, "absent", null),
                        ProgressEntryDto("x-3", "Third", "01 May", 100, "marked", 80),
                    ),
                    childDisplayName = "Rahim",
                    batchName = "Physics",
                ),
            )

        assertEquals(3, loaded.entries.size)
        assertEquals(listOf(70, null, 80), loaded.entries.map { it.marks })
        assertNull(loaded.entries[1].marks, "an absence must carry no numeric value")
        assertEquals("mark.state.absent", loaded.entries[1].stateLabel)
    }

    @Test
    fun `the series keeps the server's date order, never re-sorted`() {
        val loaded =
            assertIs<MarksUiState.ProgressLoaded>(
                MarksStateMapper.afterProgress(
                    listOf(
                        ProgressEntryDto("x-1", "First", "01 Mar", 100, "marked", 70),
                        ProgressEntryDto("x-2", "Second", "01 Mar", 100, "marked", 80),
                    ),
                    childDisplayName = "Rahim",
                    batchName = "Physics",
                ),
            )

        assertEquals(listOf("First", "Second"), loaded.entries.map { it.examTitle })
    }

    // ------------------------------------------------------------------
    // Exams.
    // ------------------------------------------------------------------

    @Test
    fun `the entered count is the server's, never a tally over rows`() {
        // A client tally is the client deciding what counts as
        // entered, and it is wrong the moment the list paginates.
        val loaded =
            assertIs<MarksUiState.ExamsLoaded>(
                MarksStateMapper.afterExams("Physics", listOf(exam(entered = 5, seats = 8))),
            )

        assertEquals(5, loaded.exams.single().enteredCount)
        assertEquals(8, loaded.exams.single().expectedCount)
    }

    @Test
    fun `an empty exam list is ExamsEmpty, not loaded with no rows`() {
        assertEquals(
            MarksUiState.ExamsEmpty("Physics"),
            MarksStateMapper.afterExams("Physics", emptyList()),
        )
    }

    @Test
    fun `retryable is read from the envelope, never inferred`() {
        val failed =
            assertIs<MarksUiState.Failed>(
                MarksStateMapper.afterError(
                    ErrorEnvelope(
                        ErrorBody(
                            code = "EXAM_NOT_AVAILABLE",
                            retryable = false,
                            messageKey = "fees.not_available",
                        ),
                    ),
                ),
            )

        assertEquals(false, failed.retryable)
    }

    @Test
    fun `a transport failure is retryable`() {
        val failed = assertIs<MarksUiState.Failed>(MarksStateMapper.afterTransportFailure())

        assertEquals(MarksStateMapper.OFFLINE_KEY, failed.messageKey)
        assertEquals(true, failed.retryable)
    }

    @Test
    fun `only a recorded result has a history, and the exam's date is kept`() {
        val loaded =
            assertIs<MarksUiState.EntryLoaded>(
                MarksStateMapper.afterResults(
                    "x-1",
                    "Mid-term",
                    100,
                    listOf("marked", "absent", "not_entered", "joined_after").map { result(state = it, marks = null) },
                    examDate = "2026-11-04",
                ),
            )

        assertEquals(listOf(true, true, false, false), loaded.rows.map { it.hasHistory })
        assertEquals("2026-11-04", loaded.examDate)
    }

    @Test
    fun `a history keeps an unknown state as its wire value rather than dropping it`() {
        val entries =
            MarksStateMapper.history(
                listOf(CorrectionDto("m-1", "future", null, "2026-10-17T06:00:00Z", superseded = false)),
            )

        assertEquals("future", entries.single().stateLabel)
    }
}
