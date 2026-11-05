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
 * The students screens' state machines and mapping decisions [0018].
 *
 * Written after the screens, from the approved decisions: the filter
 * is the server's, a student may have no batch [D3], a refused number
 * reaches the form [D2], and the server's removability is carried, not
 * derived [D4].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class StudentsViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun seat(batch: String, status: String = "active", removable: Boolean = false) =
        StudentSeatDto(
            enrollmentId = "e-$batch",
            batchId = "b-$batch",
            batchName = batch,
            feeAmount = Money.of("1200.00"),
            status = status,
            outstanding = Money.of("0.00"),
            isRemovable = removable,
        )

    private fun dto(name: String, vararg seats: StudentSeatDto, removable: Boolean = false) =
        TeacherStudentDto(
            studentId = "s-$name",
            displayName = name,
            studentState = "pending",
            guardianState = "absent",
            enrollments = seats.toList(),
            totalOutstanding = Money.of("0.00"),
            isRemovable = removable,
        )

    private val refusal =
        AuthResult.Refused(
            ErrorEnvelope(
                ErrorBody(code = "STUDENT_PHONE_TAKEN", retryable = false, messageKey = "student.phone_taken"),
            ),
        )

    private class Fake(
        var listed: AuthResult<List<TeacherStudentDto>> = AuthResult.Ok(emptyList()),
        var created: AuthResult<TeacherStudentDto>? = null,
    ) : StudentsRepository {
        val filters = mutableListOf<Pair<StudentFilter, String>>()
        var createdSeats: List<StudentSeatBody>? = null
        var addedToBatch: Pair<String, List<String>>? = null

        override suspend fun students(
            filter: StudentFilter,
            query: String,
        ): AuthResult<List<TeacherStudentDto>> {
            filters += filter to query
            return listed
        }

        override suspend fun student(studentId: String): AuthResult<TeacherStudentDto> = AuthResult.TransportFailure

        override suspend fun batches(): AuthResult<List<BatchDto>> =
            AuthResult.Ok(listOf(BatchDto(id = "b-Physics", name = "Physics", subjects = emptyList())))

        override suspend fun create(
            displayName: String,
            studentPhone: String?,
            guardianPhone: String?,
            seats: List<StudentSeatBody>,
        ): AuthResult<TeacherStudentDto> {
            createdSeats = seats
            return created ?: AuthResult.TransportFailure
        }

        override suspend fun rename(
            studentId: String,
            displayName: String?,
            studentPhone: String?,
            guardianPhone: String?,
        ): AuthResult<TeacherStudentDto> = AuthResult.TransportFailure

        override suspend fun enroll(studentId: String, batchId: String): AuthResult<TeacherStudentDto> =
            AuthResult.TransportFailure

        override suspend fun addToBatch(batchId: String, studentIds: List<String>): AuthResult<Unit> {
            addedToBatch = batchId to studentIds
            return AuthResult.Ok(Unit)
        }

        override suspend fun leaveBatch(enrollmentId: String, onDate: String): AuthResult<Unit> = AuthResult.Ok(Unit)

        override suspend fun removeSeat(enrollmentId: String): AuthResult<Unit> = AuthResult.Ok(Unit)

        override suspend fun removeStudent(studentId: String): AuthResult<Unit> = AuthResult.Ok(Unit)
    }

    @Test
    fun `a student in two batches is ONE row naming both`() = runTest(dispatcher) {
        val model = StudentsViewModel(Fake(AuthResult.Ok(listOf(dto("Rafiq", seat("Chemistry"), seat("Physics"))))))

        model.load()
        advanceUntilIdle()

        val state = assertIs<StudentsUiState.Loaded>(model.state.value)
        assertEquals(listOf("Chemistry", "Physics"), state.rows.single().batchNames)
    }

    @Test
    fun `a student in no batch is listed with no batch names`() = runTest(dispatcher) {
        val model = StudentsViewModel(Fake(AuthResult.Ok(listOf(dto("Mehedi")))))

        model.load()
        advanceUntilIdle()

        val state = assertIs<StudentsUiState.Loaded>(model.state.value)
        assertTrue(state.rows.single().batchNames.isEmpty())
    }

    @Test
    fun `the filter and the search go to the SERVER`() = runTest(dispatcher) {
        // Filtering a domain list is the server's decision [TC-9]; the
        // client sends what was chosen and renders what comes back.
        val repository = Fake()
        val model = StudentsViewModel(repository)

        model.load(StudentFilter.InBatch("b-Physics"))
        advanceUntilIdle()
        model.search("raf")
        advanceUntilIdle()

        assertEquals(StudentFilter.InBatch("b-Physics") to "raf", repository.filters.last())
    }

    @Test
    fun `nothing matching a filter is Empty and says it was filtered`() = runTest(dispatcher) {
        val model = StudentsViewModel(Fake())

        model.load(StudentFilter.Unassigned)
        advanceUntilIdle()

        assertEquals(StudentsUiState.Empty(filtered = true), model.state.value)
    }

    @Test
    fun `no students at all is Empty and not filtered`() = runTest(dispatcher) {
        val model = StudentsViewModel(Fake())

        model.load()
        advanceUntilIdle()

        assertEquals(StudentsUiState.Empty(filtered = false), model.state.value)
    }

    @Test
    fun `a transport failure is retryable`() = runTest(dispatcher) {
        val model = StudentsViewModel(Fake(AuthResult.TransportFailure))

        model.load()
        advanceUntilIdle()

        val state = assertIs<StudentsUiState.Failed>(model.state.value)
        assertTrue(state.retryable)
    }

    @Test
    fun `a number already on the list reaches the form`() = runTest(dispatcher) {
        // D2: the server refuses a duplicate number, and the refusal
        // belongs to the form that caused it.
        val model = StudentsViewModel(Fake(created = refusal))

        model.create("Rafiq", "+8801812345678", null, emptyList())
        advanceUntilIdle()

        val write = assertIs<WriteState.Failed>(model.writeState.value)
        assertEquals("student.phone_taken", write.messageKey)
    }

    @Test
    fun `a student is saved with the batches chosen and their fees`() = runTest(dispatcher) {
        val repository = Fake(created = AuthResult.Ok(dto("Rafiq")))
        val model = StudentsViewModel(repository)
        val seats = listOf(StudentSeatBody("b-Physics", null), StudentSeatBody("b-Maths", "900.00"))

        model.create("Rafiq", null, null, seats)
        advanceUntilIdle()

        assertEquals(WriteState.Saved, model.writeState.value)
        assertEquals(seats, repository.createdSeats)
    }

    @Test
    fun `the picker sends exactly the chosen students and then clears`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentsViewModel(repository)

        model.togglePick("s-1")
        model.togglePick("s-2")
        model.togglePick("s-1")
        model.addPicked("b-Physics")
        advanceUntilIdle()

        assertEquals("b-Physics" to listOf("s-2"), repository.addedToBatch)
        assertTrue(model.picked.value.isEmpty())
    }

    @Test
    fun `the detail carries the server's removability and the batches still open`() {
        val detail =
            StudentsStateMapper.detail(
                dto("Rafiq", seat("Physics", status = "inactive", removable = true), removable = true),
                listOf(BatchOption("b-Physics", "Physics", null), BatchOption("b-Maths", "Maths", null)),
            )

        assertTrue(detail.removable)
        assertEquals(false, detail.seats.single().active)
        assertTrue(detail.seats.single().removable)
        assertEquals(listOf("b-Maths"), detail.otherBatches.map(BatchOption::id))
    }
}
