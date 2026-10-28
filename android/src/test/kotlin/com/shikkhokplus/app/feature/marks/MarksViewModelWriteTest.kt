package com.shikkhokplus.app.feature.marks

import com.shikkhokplus.app.core.network.CorrectionDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.ExamDto
import com.shikkhokplus.app.core.network.MarksheetDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * Creating an exam reports through [WriteState], like the batch and
 * student forms, so the form stays open until the server answers.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class MarksViewModelWriteTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake : MarksRepository {
        var createResult: AuthResult<Unit> = AuthResult.Ok(Unit)
        var creates = 0
        var examReads = 0

        override suspend fun exams(batchId: String): AuthResult<List<ExamDto>> {
            examReads++
            return AuthResult.Ok(emptyList())
        }

        override suspend fun subjectOptions(batchId: String) =
            AuthResult.Ok(listOf(SubjectOptionDto("bs-1", "Physics")))

        override suspend fun createExam(
            batchId: String,
            title: String,
            date: String,
            totalMarks: Int,
            batchSubjectId: String,
        ): AuthResult<Unit> {
            creates++
            return createResult
        }

        var editResult: AuthResult<Unit> = AuthResult.Ok(Unit)
        val edits = mutableListOf<Triple<String, String, Int>>()
        var resultReads = 0
        var historyResult: AuthResult<List<CorrectionDto>> =
            AuthResult.Ok(
                listOf(
                    CorrectionDto("m-1", "marked", 18, "2026-10-17T06:00:00Z", superseded = true),
                    CorrectionDto("m-2", "marked", 21, "2026-10-18T06:00:00Z", superseded = false),
                ),
            )

        override suspend fun editExam(
            examId: String,
            title: String,
            date: String,
            totalMarks: Int,
        ): AuthResult<Unit> {
            edits += Triple(title, date, totalMarks)
            return editResult
        }

        override suspend fun markHistory(examId: String, enrollmentId: String) = historyResult

        override suspend fun results(examId: String): AuthResult<ExamResultsPayload> {
            resultReads++
            return AuthResult.TransportFailure
        }

        override suspend fun writeMark(
            examId: String,
            enrollmentId: String,
            resultState: String,
            marks: Int?,
        ) = AuthResult.TransportFailure

        override suspend fun marksheet(
            examId: String,
            enrollmentId: String,
            reader: MarksheetReader,
        ): AuthResult<MarksheetDto> = AuthResult.TransportFailure

        override suspend fun progress(
            enrollmentId: String,
            reader: MarksheetReader,
        ): AuthResult<List<ProgressEntryDto>> = AuthResult.TransportFailure

        override suspend fun setMarksheetVisible(batchId: String, visible: Boolean) =
            AuthResult.TransportFailure
    }

    private fun loaded(repository: Fake) =
        MarksViewModel(repository).also { it.loadExams("b-1", "Batch A") }

    @Test
    fun `a created exam reports Saved and reloads the list`() = runTest(dispatcher) {
        val repository = Fake()
        val model = loaded(repository)
        advanceUntilIdle()

        model.createExam("Weekly test", "2026-11-04", 50, "bs-1")
        advanceUntilIdle()

        assertEquals(WriteState.Saved, model.writeState.value)
        assertEquals(2, repository.examReads, "the list must reload from the server")
    }

    @Test
    fun `a refused exam reaches the form and does not reload`() = runTest(dispatcher) {
        val repository = Fake()
        repository.createResult =
            AuthResult.Refused(
                ErrorEnvelope(ErrorBody("NOT_AVAILABLE", false, "error.not_available")),
            )
        val model = loaded(repository)
        advanceUntilIdle()

        model.createExam("Weekly test", "2026-11-04", 50, "bs-1")
        advanceUntilIdle()

        val failed = assertIs<WriteState.Failed>(model.writeState.value)
        assertEquals("error.not_available", failed.messageKey)
        assertEquals(1, repository.examReads)
    }

    @Test
    fun `a second tap while saving does not create twice`() = runTest(dispatcher) {
        val repository = Fake()
        val model = loaded(repository)
        advanceUntilIdle()

        model.createExam("Weekly test", "2026-11-04", 50, "bs-1")
        model.createExam("Weekly test", "2026-11-04", 50, "bs-1")
        advanceUntilIdle()

        assertEquals(1, repository.creates)
    }

    @Test
    fun `subject options load for the form`() = runTest(dispatcher) {
        val model = MarksViewModel(Fake())

        model.loadSubjectOptions("b-1")
        assertEquals(null, model.subjectOptions.value, "null while loading")
        advanceUntilIdle()

        assertEquals(listOf(SubjectOptionDto("bs-1", "Physics")), model.subjectOptions.value)
    }

    @Test
    fun `an exam edit reports Saved and reads the results again`() = runTest(dispatcher) {
        val repository = Fake()
        val model = MarksViewModel(repository).also { it.loadResults("x-1") }
        advanceUntilIdle()

        model.editExam("Mid-term", "2026-11-04", 50)
        advanceUntilIdle()

        assertEquals(listOf(Triple("Mid-term", "2026-11-04", 50)), repository.edits)
        assertEquals(WriteState.Saved, model.writeState.value)
        assertEquals(2, repository.resultReads)
    }

    @Test
    fun `a total below a recorded mark is refused and shown on the form`() = runTest(dispatcher) {
        val repository = Fake()
        repository.editResult =
            AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, "marks.exam.total_below_recorded")))
        val model = MarksViewModel(repository).also { it.loadResults("x-1") }
        advanceUntilIdle()

        model.editExam("Mid-term", "2026-11-04", 10)
        advanceUntilIdle()

        assertEquals(WriteState.Failed("marks.exam.total_below_recorded", false), model.writeState.value)
        assertEquals(1, repository.resultReads)
    }

    @Test
    fun `a seat's history opens oldest first with the replaced marks marked`() = runTest(dispatcher) {
        val model = MarksViewModel(Fake()).also { it.loadResults("x-1") }
        advanceUntilIdle()
        val row = MarkRow("e-1", "Rahim", "mark.state.marked", 21, isEditable = true, hasHistory = true)

        model.openHistory(row)
        assertEquals(MarkHistory("Rahim"), model.history.value, "reading")
        advanceUntilIdle()

        val entries = model.history.value?.entries.orEmpty()
        assertEquals(listOf(18, 21), entries.map { it.marks })
        assertEquals(listOf(true, false), entries.map { it.superseded })
        assertEquals("mark.state.marked", entries.first().stateLabel)

        model.closeHistory()
        assertEquals(null, model.history.value)
    }

    @Test
    fun `a failed history read says so`() = runTest(dispatcher) {
        val repository = Fake()
        repository.historyResult = AuthResult.TransportFailure
        val model = MarksViewModel(repository).also { it.loadResults("x-1") }
        advanceUntilIdle()

        model.openHistory(MarkRow("e-1", "Rahim", "mark.state.absent", null, isEditable = true))
        advanceUntilIdle()

        assertEquals(true, model.history.value?.failed)
    }
}
