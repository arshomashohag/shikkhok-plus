package com.shikkhokplus.app.feature.student

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.CurrentFeeDto
import com.shikkhokplus.app.core.network.FamilyBatchViewDto
import com.shikkhokplus.app.core.network.FamilyExamDto
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.network.CalendarClassDto
import com.shikkhokplus.app.core.network.CalendarDayDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.MonthViewDto
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarUiState
import com.shikkhokplus.app.core.network.ProgressEntryDto
import com.shikkhokplus.app.core.network.StudentBatchDto
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

/** S1 and S2's loading: what is read, and what one failure stops. */
@OptIn(ExperimentalCoroutinesApi::class)
class StudentBatchViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake(
        var batches: AuthResult<List<StudentBatchDto>> =
            AuthResult.Ok(listOf(StudentBatchDto("e-1", "Physics A"))),
        var view: AuthResult<FamilyBatchViewDto> =
            AuthResult.Ok(FamilyBatchViewDto(servedAt = "2026-10-28T09:00:00Z")),
    ) : StudentRepository {
        val reads = mutableListOf<String>()
        val months = mutableListOf<YearMonth>()
        var month: AuthResult<MonthViewDto>? = null

        override suspend fun batches(): AuthResult<List<StudentBatchDto>> = batches.also { reads += "batches" }

        override suspend fun phone(): AuthResult<MeDto> =
            AuthResult.Ok(MeDto(phone = "+8801611477203")).also { reads += "phone" }

        override suspend fun batchView(enrollmentId: String): AuthResult<FamilyBatchViewDto> =
            view.also { reads += "view" }

        override suspend fun progress(enrollmentId: String): AuthResult<List<ProgressEntryDto>> =
            AuthResult.Ok<List<ProgressEntryDto>>(emptyList()).also { reads += "progress" }

        override suspend fun month(enrollmentId: String, year: Int, month: Int): AuthResult<MonthViewDto> {
            months += YearMonth(year, month)
            return this.month ?: AuthResult.Ok(monthDto(year, month))
        }

        override suspend fun exam(enrollmentId: String, examId: String): AuthResult<FamilyExamDto> =
            AuthResult.Ok(FamilyExamDto(examId, "Monthly", "2026-11-02", "Physics", 50, listOf("Heat"), "upcoming"))
                .also { reads += "exam" }
    }

    @Test
    fun `a batch loads from the list, its view and the student's results`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentBatchViewModel(repository)

        model.load("e-1")
        advanceUntilIdle()

        assertIs<StudentBatchUiState.Loaded>(model.state.value)
        assertEquals(listOf("batches", "view", "progress"), repository.reads)
    }

    @Test
    fun `a guardian's header takes the view's fee line, verifying and paid alike`() = runTest(dispatcher) {
        // The guardian's row carries no fee. The header's fee is the
        // server's line on the batch view, so a waiting claim hides Pay
        // and a paid month says when -- neither re-derived here [TC-9].
        val guardianRow = StudentBatchDto("e-1", "Physics A", childName = "Tasnim")
        val checking =
            CurrentFeeDto("2026-10", "unpaid", "2026-10-10", Money.of("1200.00"), Money.of("1200.00"), verifying = true)
        val paid =
            checking.copy(status = "paid", outstanding = Money.of("0.00"), verifying = false, paidOn = "2026-10-08")

        for ((line, check) in listOf(
            checking to { fee: FeeLine? -> assertEquals(true, fee?.verifying) },
            paid to { fee: FeeLine? -> assertEquals("2026-10-08", fee?.paidOn) },
        )) {
            val repository =
                Fake(
                    batches = AuthResult.Ok(listOf(guardianRow)),
                    view = AuthResult.Ok(FamilyBatchViewDto(servedAt = "2026-10-28T09:00:00Z", currentFee = line)),
                )
            val model = StudentBatchViewModel(repository)

            model.load("e-1")
            advanceUntilIdle()

            check(assertIs<StudentBatchUiState.Loaded>(model.state.value).view.batch.fee)
            assertEquals(listOf("batches", "view", "progress"), repository.reads)
        }
    }

    @Test
    fun `a seat not in the student's own list is not shown`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentBatchViewModel(repository)

        model.load("someone-elses")
        advanceUntilIdle()

        assertIs<StudentBatchUiState.Failed>(model.state.value)
        assertEquals(listOf("batches"), repository.reads)
    }

    @Test
    fun `the first failed read stops the rest, and retry repeats it`() = runTest(dispatcher) {
        val repository = Fake(view = AuthResult.TransportFailure)
        val model = StudentBatchViewModel(repository)

        model.load("e-1")
        advanceUntilIdle()
        val failed = assertIs<StudentBatchUiState.Failed>(model.state.value)
        assertEquals(true, failed.retryable)
        assertEquals(listOf("batches", "view"), repository.reads)

        repository.view = AuthResult.Ok(FamilyBatchViewDto(servedAt = "2026-10-28T09:00:00Z"))
        model.retry()
        advanceUntilIdle()
        assertIs<StudentBatchUiState.Loaded>(model.state.value)
    }

    @Test
    fun `the account is read for the subtitle and for the empty state`() = runTest(dispatcher) {
        val repository = Fake(batches = AuthResult.Ok(emptyList()))
        val model = MyBatchesViewModel(repository)

        model.load()
        advanceUntilIdle()

        assertEquals(MyBatchesUiState.Empty("+8801611477203"), model.state.value)
        assertEquals(listOf("batches", "phone"), repository.reads)

        val withBatches = Fake()
        val loaded = MyBatchesViewModel(withBatches)
        loaded.load()
        advanceUntilIdle()
        assertEquals(listOf("batches", "phone"), withBatches.reads)
        assertEquals("+8801611477203", (loaded.state.value as MyBatchesUiState.Loaded).phone)
    }

    @Test
    fun `the open tab lives in the model, starting on classes`() = runTest(dispatcher) {
        val model = StudentBatchViewModel(Fake())

        assertEquals(FamilyTab.CLASSES, model.tab.value)
        model.select(FamilyTab.TEACHER)
        assertEquals(FamilyTab.TEACHER, model.tab.value)
        model.load("e-1")
        advanceUntilIdle()
        assertEquals(FamilyTab.TEACHER, model.tab.value)
    }

    @Test
    fun `an exam detail loads from the exam route, and retry repeats a failure`() = runTest(dispatcher) {
        val repository = Fake()
        val model = FamilyExamViewModel(repository)

        model.load("e-1", "x-9")
        advanceUntilIdle()

        val loaded = assertIs<FamilyExamUiState.Loaded>(model.state.value)
        assertEquals(listOf("Heat"), loaded.exam.topics)
        assertEquals(listOf("exam"), repository.reads)
    }

    @Test
    fun `ensureLoaded loads once for a seat and not again`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentBatchViewModel(repository)

        model.ensureLoaded("e-1")
        advanceUntilIdle()
        model.ensureLoaded("e-1")
        advanceUntilIdle()

        assertEquals(1, repository.reads.count { it == "batches" })
    }

    private val now = { YearMonth(2026, 11) }

    @Test
    fun `the calendar opens on the current month`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentBatchViewModel(repository, now)

        model.load("e-1")
        advanceUntilIdle()

        assertEquals(listOf(YearMonth(2026, 11)), repository.months)
        assertIs<ClassCalendarUiState.Loaded>(model.calendar.value)
    }

    @Test
    fun `the shown month is kept when the same seat loads again`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentBatchViewModel(repository, now)
        model.load("e-1")
        advanceUntilIdle()

        model.pickMonth(YearMonth(2026, 10))
        advanceUntilIdle()
        model.load("e-1")
        advanceUntilIdle()

        assertEquals(listOf(YearMonth(2026, 11), YearMonth(2026, 10), YearMonth(2026, 10)), repository.months)
    }

    @Test
    fun `another seat opens on the current month again`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentBatchViewModel(repository, now)
        model.load("e-1")
        advanceUntilIdle()
        model.pickMonth(YearMonth(2026, 10))
        advanceUntilIdle()

        model.load("e-2")
        advanceUntilIdle()

        assertEquals(YearMonth(2026, 11), repository.months.last())
    }

    @Test
    fun `a failed month does not fail the batch, and retry reads it again`() = runTest(dispatcher) {
        val repository = Fake().apply { month = AuthResult.TransportFailure }
        val model = StudentBatchViewModel(repository, now)

        model.load("e-1")
        advanceUntilIdle()

        assertIs<StudentBatchUiState.Loaded>(model.state.value)
        assertEquals(true, assertIs<ClassCalendarUiState.Failed>(model.calendar.value).retryable)

        repository.month = null
        model.retryMonth()
        advanceUntilIdle()
        assertIs<ClassCalendarUiState.Loaded>(model.calendar.value)
    }

    @Test
    fun `a class is found in the loaded month by its session id`() = runTest(dispatcher) {
        val model = StudentBatchViewModel(Fake(), now)
        assertEquals(null, model.classOf("s-1"))

        model.load("e-1")
        advanceUntilIdle()

        assertEquals("Heat", model.classOf("s-1")?.topic)
        assertEquals(null, model.classOf("nope"))
    }

    @Test
    fun `a detail built first opens the calendar on the month it was given`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentBatchViewModel(repository, now)

        model.ensureLoaded("e-1", YearMonth(2026, 9))
        advanceUntilIdle()

        assertEquals(listOf(YearMonth(2026, 9)), repository.months)
    }
}

private fun monthDto(year: Int, month: Int): MonthViewDto =
    MonthViewDto(
        year = year,
        month = month,
        firstMonth = "2026-01",
        lastMonth = "2026-12",
        days =
            listOf(
                CalendarDayDto(
                    "%04d-%02d-14".format(year, month),
                    "taken",
                    listOf(
                        CalendarClassDto(
                            sessionId = "s-1",
                            date = "%04d-%02d-14".format(year, month),
                            startTime = "16:00:00",
                            state = "taken",
                            topic = "Heat",
                            mark = "present",
                        ),
                    ),
                ),
            ),
    )
