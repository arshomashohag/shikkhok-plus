package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.network.CalendarClassDto
import com.shikkhokplus.app.core.network.CalendarDayDto
import com.shikkhokplus.app.core.network.MonthViewDto
import com.shikkhokplus.app.core.ui.CalendarDayUi
import com.shikkhokplus.app.core.ui.CalendarState
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

/** The Classes tab's calendar: months it asks for and where taps lead. */
@OptIn(ExperimentalCoroutinesApi::class)
class ClassCalendarViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class FakeCalendar(var result: AuthResult<MonthViewDto>? = null) : ClassCalendarRepository {
        val asked = mutableListOf<Triple<String, Int, Int>>()

        override suspend fun month(batchId: String, year: Int, month: Int): AuthResult<MonthViewDto> {
            asked += Triple(batchId, year, month)
            return result ?: AuthResult.Ok(MonthViewDto(year, month, "2026-01", "2026-12"))
        }
    }

    private fun dto(id: String, recordable: Boolean = false, plannable: Boolean = false) =
        CalendarClassDto(
            sessionId = id,
            date = "2026-11-16",
            startTime = "16:00:00",
            state = "upcoming",
            plannable = plannable,
            recordable = recordable,
        )

    private fun model(fake: FakeCalendar) =
        ClassCalendarViewModel(fake, currentMonth = { YearMonth(2026, 11) })

    @Test
    fun `it loads the current month, then a picked month`() = runTest(dispatcher) {
        val fake = FakeCalendar()
        val model = model(fake)

        model.load("b-1")
        advanceUntilIdle()
        model.pick(YearMonth(2026, 12))
        advanceUntilIdle()

        assertEquals(listOf(Triple("b-1", 2026, 11), Triple("b-1", 2026, 12)), fake.asked)
        val loaded = assertIs<ClassCalendarUiState.Loaded>(model.state.value)
        assertEquals(YearMonth(2026, 12), loaded.view.month)
    }

    @Test
    fun `loading the same batch again keeps the month on screen`() = runTest(dispatcher) {
        val fake = FakeCalendar()
        val model = model(fake)
        model.load("b-1")
        advanceUntilIdle()
        model.pick(YearMonth(2026, 9))
        advanceUntilIdle()

        model.load("b-1")
        advanceUntilIdle()
        model.load("b-2")
        advanceUntilIdle()

        assertEquals(Triple("b-1", 2026, 9), fake.asked[2])
        assertEquals(Triple("b-2", 2026, 11), fake.asked[3])
    }

    @Test
    fun `reload asks for the month on screen again`() = runTest(dispatcher) {
        val fake = FakeCalendar()
        val model = model(fake)
        model.load("b-1")
        advanceUntilIdle()
        model.pick(YearMonth(2026, 9))
        advanceUntilIdle()

        model.reload()
        advanceUntilIdle()

        assertEquals(Triple("b-1", 2026, 9), fake.asked.last())
        assertEquals(3, fake.asked.size)
    }

    @Test
    fun `a failed read is a failure with the server's retry advice`() = runTest(dispatcher) {
        val fake = FakeCalendar(AuthResult.Refused(envelope("error.unexpected")))
        val model = model(fake)

        model.load("b-1")
        advanceUntilIdle()

        val failed = assertIs<ClassCalendarUiState.Failed>(model.state.value)
        assertEquals("error.unexpected", failed.messageKey)
        assertEquals(false, failed.retryable)
    }

    @Test
    fun `no connection is a retryable failure`() = runTest(dispatcher) {
        val model = model(FakeCalendar(AuthResult.TransportFailure))

        model.load("b-1")
        advanceUntilIdle()

        val failed = assertIs<ClassCalendarUiState.Failed>(model.state.value)
        assertEquals(true, failed.retryable)
    }

    @Test
    fun `a recordable class opens the class screen, a plannable one the plan screen`() {
        val record = calendarClass(recordable = true, plannable = true)
        val plan = calendarClass(plannable = true)
        val neither = calendarClass()

        assertIs<ClassTarget.Record>(ClassTapRouter.forClass(record))
        assertIs<ClassTarget.Plan>(ClassTapRouter.forClass(plan))
        assertIs<ClassTarget.ReadOnly>(ClassTapRouter.forClass(neither))
    }

    @Test
    fun `routing ignores the class's state and date, only the flags decide`() {
        val taken = calendarClass(state = CalendarState.TAKEN, date = "2020-01-01")
        val upcoming = calendarClass(state = CalendarState.UPCOMING, date = "2099-01-01", recordable = true)

        assertIs<ClassTarget.ReadOnly>(ClassTapRouter.forClass(taken))
        assertIs<ClassTarget.Record>(ClassTapRouter.forClass(upcoming))
    }

    @Test
    fun `a day with one class opens it, several offer a list, none opens nothing`() {
        val one = ClassTapRouter.forDay(listOf(calendarClass("a", plannable = true)))
        val two = ClassTapRouter.forDay(listOf(calendarClass("a"), calendarClass("b", recordable = true)))

        assertIs<ClassTarget.Plan>(one)
        assertEquals(listOf("a", "b"), assertIs<ClassTarget.Choose>(two).classes.map { it.sessionId })
        assertNull(ClassTapRouter.forDay(emptyList()))
    }

    @Test
    fun `tapping a day with several classes lists them, and choosing one routes by its flags`() =
        runTest(dispatcher) {
            val fake =
                FakeCalendar(
                    AuthResult.Ok(
                        MonthViewDto(
                            2026,
                            11,
                            "2026-01",
                            "2026-12",
                            days =
                                listOf(
                                    CalendarDayDto(
                                        "2026-11-16",
                                        "upcoming",
                                        listOf(dto("a", plannable = true), dto("b", recordable = true)),
                                    ),
                                ),
                        ),
                    ),
                )
            val model = model(fake)
            model.load("b-1")
            advanceUntilIdle()
            val day = (model.state.value as ClassCalendarUiState.Loaded).view.days.single()

            model.tapDay(day)
            val list = assertIs<ClassTarget.Choose>(model.target.value)
            model.chooseClass(list.classes.last())

            assertEquals("b", assertIs<ClassTarget.Record>(model.target.value).clazz.sessionId)
            model.closeTarget()
            assertNull(model.target.value)
        }

    @Test
    fun `tapping a day with no classes opens nothing`() {
        val model = model(FakeCalendar())

        model.tapDay(CalendarDayUi("2026-11-02", CalendarState.TAKEN, emptyList()))

        assertNull(model.target.value)
    }
}
