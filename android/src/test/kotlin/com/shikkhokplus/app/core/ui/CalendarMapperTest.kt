package com.shikkhokplus.app.core.ui

import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.network.MonthViewDto
import kotlinx.serialization.json.Json
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** The wire month becomes the model the calendar draws, and never crashes on a new state [D-26]. */
class CalendarMapperTest {

    private val json = Json { ignoreUnknownKeys = true }

    private fun klass(state: String, mark: String? = null) =
        """{"session_id":"s1","date":"2026-11-05","start_time":"16:00:00","state":"$state",
            "plannable":true,"recordable":false${mark?.let { ""","mark":"$it"""" } ?: ""}}"""

    private fun month(days: String) =
        json.decodeFromString<MonthViewDto>(
            """{"year":2026,"month":11,"first_month":"2026-09","last_month":"2026-12",
                "served_at":"2026-11-01T00:00:00Z","days":[$days]}""",
        )

    @Test
    fun `a full month maps with its bounds and classes`() {
        val ui = CalendarMapper.toUi(
            month("""{"date":"2026-11-05","state":"taken","classes":[${klass("taken", "present")}]}"""),
        )
        assertEquals(YearMonth(2026, 11), ui.month)
        assertEquals(YearMonth(2026, 9), ui.firstMonth)
        assertEquals(YearMonth(2026, 12), ui.lastMonth)
        val day = ui.days.single()
        assertEquals(CalendarState.TAKEN, day.state)
        assertEquals(5, day.dayOfMonth)
        assertEquals(CalendarMark.PRESENT, day.classes.single().mark)
        assertTrue(day.classes.single().plannable)
    }

    @Test
    fun `versions and the server's today are carried`() {
        val dto =
            json.decodeFromString<MonthViewDto>(
                """{"year":2026,"month":11,"first_month":"2026-09","last_month":"2026-12","today":"2026-11-05",
                    "days":[{"date":"2026-11-05","state":"today","classes":[{"session_id":"s1",
                    "date":"2026-11-05","start_time":"16:00:00","state":"today","plannable":true,
                    "recordable":false,"topic_version":4,"attendance_version":2}]}]}""",
            )
        val ui = CalendarMapper.toUi(dto)
        assertEquals("2026-11-05", ui.today)
        val clazz = ui.days.single().classes.single()
        assertEquals(4, clazz.topicVersion)
        assertEquals(2, clazz.attendanceVersion)
    }

    @Test
    fun `a day with an unknown state is dropped`() {
        val ui = CalendarMapper.toUi(
            month(
                """{"date":"2026-11-05","state":"mystery","classes":[${klass("taken")}]},
                   {"date":"2026-11-06","state":"upcoming","classes":[${klass("upcoming")}]}""",
            ),
        )
        assertEquals(listOf("2026-11-06"), ui.days.map { it.date })
    }

    @Test
    fun `a class with an unknown state is dropped and an unknown mark is null`() {
        val ui = CalendarMapper.toUi(
            month(
                """{"date":"2026-11-05","state":"taken",
                    "classes":[${klass("mystery")},${klass("taken", "excused")}]}""",
            ),
        )
        val classes = ui.days.single().classes
        assertEquals(1, classes.size)
        assertNull(classes.single().mark)
    }

    @Test
    fun `unreadable bounds fall back to the shown month`() {
        val dto = month("").copy(firstMonth = "nope", lastMonth = "2026-13")
        val ui = CalendarMapper.toUi(dto)
        assertEquals(YearMonth(2026, 11), ui.firstMonth)
        assertEquals(YearMonth(2026, 11), ui.lastMonth)
    }

    @Test
    fun `year month arithmetic crosses year ends and sizes the grid`() {
        assertEquals(YearMonth(2027, 1), YearMonth(2026, 12).plusMonths(1))
        assertEquals(YearMonth(2025, 12), YearMonth(2026, 1).plusMonths(-1))
        assertEquals(29, YearMonth(2028, 2).lengthOfMonth())
        assertEquals(0, YearMonth(2026, 11).leadingBlanks())
        assertEquals("2026-03", YearMonth(2026, 3).toString())
        assertTrue(YearMonth(2026, 9) < YearMonth(2026, 11))
    }

    @Test
    fun `leading blanks follow the weekday the month starts on`() {
        assertEquals(2, YearMonth(2026, 12).leadingBlanks())
        assertEquals(6, YearMonth(2026, 8).leadingBlanks())
    }

    @Test
    fun `february has 28 days in 2027 and 29 in 2028`() {
        assertEquals(28, YearMonth(2027, 2).lengthOfMonth())
        assertEquals(29, YearMonth(2028, 2).lengthOfMonth())
    }
}
