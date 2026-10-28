package com.shikkhokplus.app.feature.marks

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.ExamDto
import com.shikkhokplus.app.core.network.MarksheetDto
import com.shikkhokplus.app.core.network.ProgressDto
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

        override suspend fun results(examId: String) = AuthResult.TransportFailure

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

        override suspend fun progress(enrollmentId: String): AuthResult<ProgressDto> =
            AuthResult.TransportFailure

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
}
