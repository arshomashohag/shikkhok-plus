package com.shikkhokplus.app.feature.myexams

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.ExamExaminerDto
import com.shikkhokplus.app.core.network.ExamResultDto
import com.shikkhokplus.app.core.network.ExaminerResultsDto
import com.shikkhokplus.app.core.network.MarkWriteBody
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.MyExamDto
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
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** An examiner's exams and marks, and the manager's examiner control. */
@OptIn(ExperimentalCoroutinesApi::class)
class MyExamsViewModelsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val exam =
        MyExamDto(
            examId = "x-1",
            centreName = "Alo Coaching",
            batchName = "Physics",
            subjectName = "Physics",
            title = "Class test",
            date = "2026-11-06",
            totalMarks = 20,
        )

    private inner class Fake : MyExamsRepository {
        var sheet =
            ExaminerResultsDto(
                exam = exam,
                results =
                    listOf(
                        ExamResultDto("e-1", "Rafi", "marked", 17.5),
                        ExamResultDto("e-2", "Mitu", "not_entered"),
                        ExamResultDto("e-3", "Nila", "joined_after"),
                    ),
                writable = true,
            )
        var writeResult: AuthResult<Unit> = AuthResult.Ok(Unit)
        val marks = mutableListOf<MarkWriteBody>()
        var published = 0
        var reads = 0

        override suspend fun exams(): AuthResult<List<MyExamDto>> = AuthResult.Ok(listOf(exam))

        override suspend fun results(examId: String): AuthResult<ExaminerResultsDto> {
            reads++
            return AuthResult.Ok(sheet)
        }

        override suspend fun mark(examId: String, body: MarkWriteBody): AuthResult<Unit> {
            marks += body
            return writeResult
        }

        override suspend fun publish(examId: String): AuthResult<Unit> {
            published++
            return writeResult
        }
    }

    @Test
    fun `my exams load as the server lists them`() = runTest(dispatcher) {
        val model = MyExamsViewModel(Fake())
        model.load()
        advanceUntilIdle()

        val loaded = assertIs<Loadable.Loaded<List<MyExamDto>>>(model.state.value)
        assertEquals(listOf("x-1"), loaded.value.map { it.examId })
    }

    @Test
    fun `a recorded mark is typed back in, and a typed Bangla mark is sent as a number`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MyExamMarksViewModel(fake, "x-1")
        model.load()
        advanceUntilIdle()
        assertEquals("17.5", model.state.value.typed["e-1"])

        model.type("e-2", "১৮")
        model.save("e-2")
        advanceUntilIdle()

        assertEquals(listOf(MarkWriteBody("e-2", "marked", 18.0)), fake.marks)
        assertEquals(2, fake.reads, "the sheet is read again, its states the server's")
        assertEquals(MarksNotice.SAVED, model.state.value.notice)
    }

    @Test
    fun `nothing is sent while the typed mark is not a number`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MyExamMarksViewModel(fake, "x-1")
        model.load()
        advanceUntilIdle()

        model.type("e-2", "")
        model.save("e-2")
        advanceUntilIdle()

        assertTrue(fake.marks.isEmpty())
    }

    @Test
    fun `absent carries no marks at all`() = runTest(dispatcher) {
        val fake = Fake()
        val model = MyExamMarksViewModel(fake, "x-1")
        model.load()
        advanceUntilIdle()

        model.absent("e-2")
        advanceUntilIdle()

        assertEquals(listOf(MarkWriteBody("e-2", "absent", null)), fake.marks)
    }

    @Test
    fun `an exam moved to another examiner shows the server's refusal`() = runTest(dispatcher) {
        val fake = Fake()
        fake.writeResult = AuthResult.Refused(ErrorEnvelope(ErrorBody("EXAM_REASSIGNED", false, "exam.reassigned")))
        val model = MyExamMarksViewModel(fake, "x-1")
        model.load()
        advanceUntilIdle()

        model.publish()
        advanceUntilIdle()

        assertEquals(1, fake.published)
        assertEquals("exam.reassigned", model.state.value.failureKey)
        assertNull(model.state.value.notice)
    }

    @Test
    fun `published results offer no second publish, and a closed sheet takes no marks`() = runTest(dispatcher) {
        val fake = Fake()
        fake.sheet = fake.sheet.copy(exam = exam.copy(published = true))
        val model = MyExamMarksViewModel(fake, "x-1")
        model.load()
        advanceUntilIdle()
        assertFalse(model.state.value.canPublish)
        model.publish()

        fake.sheet = fake.sheet.copy(writable = false)
        model.retry()
        advanceUntilIdle()
        model.absent("e-2")
        advanceUntilIdle()

        assertEquals(0, fake.published)
        assertTrue(fake.marks.isEmpty())
    }

    private class FakeExaminer : ExaminerRepository {
        var exam = ExamExaminerDto("x-1", examinerMemberId = "m-1", examinerName = "Karim")
        var result: AuthResult<ExamExaminerDto>? = null
        val set = mutableListOf<String?>()

        override suspend fun exam(examId: String): AuthResult<ExamExaminerDto> = AuthResult.Ok(exam)

        override suspend fun members(): AuthResult<List<MemberDto>> =
            AuthResult.Ok(
                listOf(
                    MemberDto("m-1", "Karim", "+880", "teacher", "accepted"),
                    MemberDto("m-2", "Salma", "+880", "teacher", "pending"),
                    MemberDto("m-3", "Gone", "+880", "teacher", "accepted", revoked = true),
                ),
            )

        override suspend fun setExaminer(examId: String, memberId: String?): AuthResult<ExamExaminerDto> {
            set += memberId
            return result ?: AuthResult.Ok(exam.copy(examinerMemberId = memberId))
        }
    }

    @Test
    fun `the examiner can be changed to a live member or to nobody`() = runTest(dispatcher) {
        val fake = FakeExaminer()
        val model = ExaminerViewModel(fake, "x-1")
        model.load()
        advanceUntilIdle()
        assertEquals(listOf("m-1", "m-2"), model.state.value.members.map { it.memberId })

        model.choose("m-3")
        model.choose("m-1")
        model.choose("m-2")
        advanceUntilIdle()
        model.choose(null)
        advanceUntilIdle()

        assertEquals(listOf("m-2", null), fake.set)
        assertNull(model.state.value.exam?.examinerMemberId)
        assertTrue(model.state.value.changed)
    }

    @Test
    fun `a cancelled exam's examiner is not changed`() = runTest(dispatcher) {
        val fake = FakeExaminer().apply { exam = exam.copy(cancelled = true) }
        val model = ExaminerViewModel(fake, "x-1")
        model.load()
        advanceUntilIdle()

        model.choose("m-2")
        advanceUntilIdle()

        assertTrue(fake.set.isEmpty())
    }
}
