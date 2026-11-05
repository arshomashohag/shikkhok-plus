package com.shikkhokplus.app.feature.students

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.StudentSeatBody
import com.shikkhokplus.app.core.network.StudentSeatDto
import com.shikkhokplus.app.core.network.TeacherStudentDto
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
import kotlin.test.assertTrue

/**
 * One student's screen: load, every action, and refusals [0018].
 *
 * Every action reloads from the server afterwards; none edits the
 * loaded student locally [TC-8, D-9].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class StudentDetailViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val seat =
        StudentSeatDto(
            enrollmentId = "e-1",
            batchId = "b-1",
            batchName = "Physics",
            feeAmount = Money.of("1200.00"),
            status = "active",
            outstanding = Money.of("1200.00"),
            isRemovable = false,
        )

    private val loaded =
        TeacherStudentDto(
            studentId = "s-1",
            displayName = "Rafiq",
            studentState = "accepted",
            guardianState = "absent",
            enrollments = listOf(seat),
            totalOutstanding = Money.of("1200.00"),
            isRemovable = false,
        )

    private val owes =
        AuthResult.Refused(
            ErrorEnvelope(ErrorBody(code = "STUDENT_OWES", retryable = false, messageKey = "student.remove.owes")),
        )

    private class Fake(
        var read: AuthResult<TeacherStudentDto>,
        var write: AuthResult<Unit> = AuthResult.Ok(Unit),
    ) : StudentsRepository {
        var reads = 0
        val actions = mutableListOf<String>()

        override suspend fun students(filter: StudentFilter, query: String) =
            AuthResult.Ok(emptyList<TeacherStudentDto>())

        override suspend fun student(studentId: String): AuthResult<TeacherStudentDto> {
            reads += 1
            return read
        }

        override suspend fun batches(): AuthResult<List<BatchDto>> =
            AuthResult.Ok(
                listOf(
                    BatchDto(id = "b-1", name = "Physics", subjects = emptyList()),
                    BatchDto(id = "b-2", name = "Maths", subjects = emptyList()),
                ),
            )

        override suspend fun create(
            displayName: String,
            studentPhone: String?,
            guardianPhone: String?,
            seats: List<StudentSeatBody>,
        ): AuthResult<TeacherStudentDto> = read

        override suspend fun rename(
            studentId: String,
            displayName: String?,
            studentPhone: String?,
            guardianPhone: String?,
        ): AuthResult<TeacherStudentDto> {
            actions += "rename:$displayName"
            return read
        }

        override suspend fun enroll(studentId: String, batchId: String): AuthResult<TeacherStudentDto> {
            actions += "enroll:$batchId"
            return read
        }

        override suspend fun addToBatch(batchId: String, studentIds: List<String>) = write

        override suspend fun leaveBatch(enrollmentId: String, onDate: String): AuthResult<Unit> {
            actions += "leave:$enrollmentId:$onDate"
            return write
        }

        override suspend fun removeSeat(enrollmentId: String): AuthResult<Unit> {
            actions += "remove-seat:$enrollmentId"
            return write
        }

        override suspend fun removeStudent(studentId: String): AuthResult<Unit> {
            actions += "remove:$studentId"
            return write
        }
    }

    @Test
    fun `a loaded student offers only the batches they are not in`() = runTest(dispatcher) {
        val model = StudentDetailViewModel(Fake(AuthResult.Ok(loaded)))

        model.load("s-1")
        advanceUntilIdle()

        val state = assertIs<StudentDetailUiState.Loaded>(model.state.value)
        assertEquals(listOf("b-2"), state.student.otherBatches.map(BatchOption::id))
        assertEquals(Money.of("1200.00"), state.student.totalOutstanding)
    }

    @Test
    fun `a failed read carries the server's retryable flag`() = runTest(dispatcher) {
        val model = StudentDetailViewModel(Fake(AuthResult.TransportFailure))

        model.load("s-1")
        advanceUntilIdle()

        val state = assertIs<StudentDetailUiState.Failed>(model.state.value)
        assertTrue(state.retryable)
    }

    @Test
    fun `every action reloads the student from the server`() = runTest(dispatcher) {
        val repository = Fake(AuthResult.Ok(loaded))
        val model = StudentDetailViewModel(repository)
        model.load("s-1")
        advanceUntilIdle()

        model.enroll("b-2")
        advanceUntilIdle()
        model.leave("e-1", "2026-11-05")
        advanceUntilIdle()
        model.removeSeat("e-1")
        advanceUntilIdle()
        model.edit("Rafiqul", null, null)
        advanceUntilIdle()

        assertEquals(
            listOf("enroll:b-2", "leave:e-1:2026-11-05", "remove-seat:e-1", "rename:Rafiqul"),
            repository.actions,
        )
        assertEquals(5, repository.reads, "one load, then one reload per action")
        assertEquals(WriteState.Saved, model.writeState.value)
    }

    @Test
    fun `a refused removal is shown and the student stays`() = runTest(dispatcher) {
        // D4: removal is the server's decision; a refusal never closes the screen.
        val model = StudentDetailViewModel(Fake(AuthResult.Ok(loaded), write = owes))
        model.load("s-1")
        advanceUntilIdle()

        model.removeStudent()
        advanceUntilIdle()

        val write = assertIs<WriteState.Failed>(model.writeState.value)
        assertEquals("student.remove.owes", write.messageKey)
        assertIs<StudentDetailUiState.Loaded>(model.state.value)
    }

    @Test
    fun `an agreed removal closes the screen`() = runTest(dispatcher) {
        val model = StudentDetailViewModel(Fake(AuthResult.Ok(loaded)))
        model.load("s-1")
        advanceUntilIdle()

        model.removeStudent()
        advanceUntilIdle()

        assertEquals(StudentDetailUiState.Removed, model.state.value)
        model.acknowledgeWrite()
        assertEquals(WriteState.Idle, model.writeState.value)
    }
}
