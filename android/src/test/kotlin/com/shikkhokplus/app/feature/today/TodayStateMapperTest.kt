package com.shikkhokplus.app.feature.today

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.OutstandingDto
import com.shikkhokplus.app.core.network.TodayClassDto
import com.shikkhokplus.app.core.network.TodayDto
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
import kotlin.test.assertNull

/**
 * T1's mapping and loading, on the plain JVM so the coverage figure sees
 * them. Every figure and every "next" is the server's; these pin that
 * the client shows them and decides nothing.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class TodayStateMapperTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun lesson(
        id: String,
        start: String,
        next: Boolean = false,
        topic: String? = null,
        exam: String? = null,
        status: String = "scheduled",
    ) = TodayClassDto(
        sessionId = id,
        batchId = "b-1",
        batchName = "Batch A",
        subjectName = "Physics",
        startTime = start,
        status = status,
        topic = topic,
        topicLogged = topic != null,
        attendanceVersion = 0,
        topicVersion = 0,
        isNext = next,
        startsInMinutes = if (next) 35 else null,
        examId = exam?.let { "x-1" },
        examTitle = exam,
    )

    private fun day(
        classes: List<TodayClassDto> = emptyList(),
        overdueStudents: Int = 12,
        hasBatches: Boolean = true,
    ) = TodayDto(
        date = "2026-10-17",
        outstanding = OutstandingDto(Money.of("48600.00"), Money.of("31200.00"), overdueStudents, 7),
        classes = classes,
        toVerifyCount = 0,
        hasBatches = hasBatches,
    )

    @Test
    fun `no batch yet is the first run, not three empty sections`() {
        assertIs<TodayUiState.FirstRun>(TodayStateMapper.afterLoad(day(hasBatches = false)))
    }

    @Test
    fun `nothing overdue hides the overdue chip`() {
        val loaded = assertIs<TodayUiState.Loaded>(TodayStateMapper.afterLoad(day(overdueStudents = 0)))

        assertEquals(false, loaded.owed.showOverdue)
    }

    @Test
    fun `a blank topic is logged with nothing to show, and an unknown status fails`() {
        val blank = TodayStateMapper.afterLoad(day(listOf(lesson("s-1", "10:00:00", topic = " "))))
        val loaded = assertIs<TodayUiState.Loaded>(blank)
        assertNull(loaded.classes.single().topic)
        assertEquals("10:00", loaded.classes.single().startTime)

        val moved = TodayStateMapper.afterLoad(day(listOf(lesson("s-1", "10:00:00", status = "moved"))))
        assertIs<TodayUiState.Failed>(moved)
    }

    @Test
    fun `the view model loads the day and retries when asked`() = runTest(dispatcher) {
        var answer: AuthResult<TodayDto> = AuthResult.TransportFailure
        val model = TodayViewModel(object : TodayRepository {
            override suspend fun today() = answer
        })

        model.load()
        advanceUntilIdle()
        assertIs<TodayUiState.Failed>(model.state.value)

        answer = AuthResult.Ok(day())
        model.retry()
        advanceUntilIdle()
        assertIs<TodayUiState.Loaded>(model.state.value)
    }

}
