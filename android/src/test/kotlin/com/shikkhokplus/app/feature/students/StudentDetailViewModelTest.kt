package com.shikkhokplus.app.feature.students

import com.shikkhokplus.app.core.model.EmailEdit
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
            clientMutationId: String?,
            studentEmail: String?,
            guardianEmail: String?,
        ): AuthResult<TeacherStudentDto> = read

        /** Each rename's two email edits. */
        val emailEdits = mutableListOf<Pair<EmailEdit, EmailEdit>>()

        /** The answer to the next rename, when set; the read otherwise. */
        var renameResult: AuthResult<TeacherStudentDto>? = null

        override suspend fun rename(
            studentId: String,
            displayName: String?,
            studentPhone: String?,
            guardianPhone: String?,
            studentEmail: EmailEdit,
            guardianEmail: EmailEdit,
        ): AuthResult<TeacherStudentDto> {
            actions += "rename:$displayName"
            emailEdits += studentEmail to guardianEmail
            return renameResult ?: read
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

    // --- U3: the emails on the edit [W7.5, W7.6, W7.7] ------------------------

    @Test
    fun `an edit passes each email's change through, kept, set or cleared`() = runTest(dispatcher) {
        val repository = Fake(AuthResult.Ok(loaded))
        val model = StudentDetailViewModel(repository)
        model.load("s-1")
        advanceUntilIdle()

        model.edit(null, null, null, EmailEdit.Set("rafiq@example.com"), EmailEdit.Clear)
        advanceUntilIdle()
        model.edit("Rafiqul", null, null)
        advanceUntilIdle()

        assertEquals(
            listOf(
                EmailEdit.Set("rafiq@example.com") to EmailEdit.Clear,
                EmailEdit.Unchanged to EmailEdit.Unchanged,
            ),
            repository.emailEdits,
        )
        assertEquals(WriteState.Saved, model.writeState.value)
    }

    @Test
    fun `a taken email on edit is refused and the student stays`() = runTest(dispatcher) {
        val repository = Fake(AuthResult.Ok(loaded))
        repository.renameResult =
            AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, "student.email.taken")))
        val model = StudentDetailViewModel(repository)
        model.load("s-1")
        advanceUntilIdle()

        model.edit(null, null, null, EmailEdit.Set("taken@example.com"), EmailEdit.Unchanged)
        advanceUntilIdle()

        assertEquals(WriteState.Failed("student.email.taken", retryable = false), model.writeState.value)
        assertIs<StudentDetailUiState.Loaded>(model.state.value)
    }

    @Test
    fun `the detail's contact lines are the phone, else the email, both when both`() {
        val options = emptyList<BatchOption>()
        val emailOnly = StudentsStateMapper.detail(loaded.copy(studentEmail = "rafiq@example.com"), options)
        val both =
            StudentsStateMapper.detail(
                loaded.copy(guardianPhone = "+8801711223344", guardianEmail = "parent@example.com"),
                options,
            )
        val neither = StudentsStateMapper.detail(loaded, options)

        assertEquals("rafiq@example.com", emailOnly.studentContactLine)
        assertEquals("+8801711223344 · parent@example.com", both.guardianContactLine)
        assertEquals(null, neither.studentContactLine)
        assertEquals(null, neither.guardianContactLine)
    }

    @Test
    fun `an emptied email is a clear, an untouched one unchanged, a new one a set`() {
        assertEquals(EmailEdit.Unchanged, EmailEdit.of("rafiq@example.com", " rafiq@example.com "))
        assertEquals(EmailEdit.Clear, EmailEdit.of("rafiq@example.com", "  "))
        assertEquals(EmailEdit.Set("new@example.com"), EmailEdit.of("rafiq@example.com", "new@example.com "))
        assertEquals(EmailEdit.Unchanged, EmailEdit.of(null, ""))
        assertTrue("new@example.com" !in EmailEdit.Set("new@example.com").toString())
    }

    @Test
    fun `the detail, a row and a new student never print a contact`() {
        val detail =
            StudentsStateMapper.detail(
                loaded.copy(
                    studentPhone = "+8801999999999",
                    guardianEmail = "sentinel@example.invalid",
                ),
                emptyList(),
            )
        val row = StudentListRow("s-1", "Rafiq", "sentinel@example.invalid", emptyList())
        val new =
            com.shikkhokplus.app.feature.students.ui.NewStudent(
                "Rafiq",
                "+8801999999999",
                null,
                emptyList(),
                "sentinel@example.invalid",
                null,
            )

        val withEmail = loaded.copy(studentEmail = "sentinel@example.invalid")
        listOf(detail.toString(), row.toString(), new.toString(), withEmail.toString())
            .forEach { printed ->
                assertTrue("+8801999999999" !in printed && "sentinel@example.invalid" !in printed, printed)
            }
    }
}
