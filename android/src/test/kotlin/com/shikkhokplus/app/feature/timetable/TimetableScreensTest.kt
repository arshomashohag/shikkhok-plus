package com.shikkhokplus.app.feature.timetable

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.network.MemberDto
import com.shikkhokplus.app.core.network.RoomDto
import com.shikkhokplus.app.core.network.TimetableClassDto
import com.shikkhokplus.app.feature.timetable.ui.RoomsActions
import com.shikkhokplus.app.feature.timetable.ui.RoomsScreen
import com.shikkhokplus.app.feature.timetable.ui.TAG_TIMETABLE_FAILURE
import com.shikkhokplus.app.feature.timetable.ui.TimetableActions
import com.shikkhokplus.app.feature.timetable.ui.TimetableScreen
import com.shikkhokplus.app.feature.timetable.ui.roomArchiveTag
import com.shikkhokplus.app.feature.timetable.ui.swapChoiceTag
import com.shikkhokplus.app.feature.timetable.ui.teacherChoiceTag
import com.shikkhokplus.app.feature.timetable.ui.timetableClassTag
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The centre timetable and rooms, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TimetableScreensTest {

    @get:Rule
    val compose = createComposeRule()

    private fun klass(id: String, start: String, teacher: String? = "Karim", status: String = "scheduled") =
        TimetableClassDto(
            sessionId = id,
            batchId = "b-1",
            batchName = "Physics",
            date = "2026-11-06",
            startTime = start,
            status = status,
            teacherMemberId = teacher?.let { "m-1" },
            teacherName = teacher,
            roomName = "Room A",
        )

    private fun loaded(vararg classes: TimetableClassDto) =
        TimetableBody.Loaded(
            listOf("2026-11-06" to classes.toList()) + weekFrom("2026-11-07").take(6).map { it to emptyList() },
        )

    @Test
    fun `a class shows its teacher and room, an unassigned one says so, and tapping opens it`() {
        val opened = mutableListOf<String>()
        compose.setContent {
            TimetableScreen(
                state =
                    TimetableUiState(
                        weekStart = "2026-11-06",
                        body = loaded(klass("c-1", "16:00"), klass("c-2", "17:00", teacher = null)),
                    ),
                actions = TimetableActions(onOpen = { opened += it }),
            )
        }

        compose.onNodeWithText("Karim · Room A").assertIsDisplayed()
        compose.onNodeWithText("No teacher yet · Room A").assertIsDisplayed()
        compose.onNodeWithTag(timetableClassTag("c-1")).performClick()
        assertEquals(listOf("c-1"), opened)
    }

    @Test
    fun `the change sheet offers teachers and the day's swaps and shows a clash`() {
        val chosen = mutableListOf<String?>()
        val swaps = mutableListOf<String?>()
        val target = klass("c-1", "16:00")
        compose.setContent {
            TimetableScreen(
                state =
                    TimetableUiState(
                        weekStart = "2026-11-06",
                        body = loaded(target, klass("c-2", "17:00")),
                        teachers = listOf(MemberDto("m-2", "Salma", "+880", "teacher", "accepted")),
                        change = ClassChange(target),
                        failure = TimetableFailure("schedule.clash", "Chemistry", "16:30"),
                    ),
                actions = TimetableActions(onTeacher = { chosen += it }, onSwapWith = { swaps += it }),
            )
        }

        compose.onNodeWithTag(teacherChoiceTag("m-2")).performClick()
        compose.onNodeWithTag(swapChoiceTag("c-2")).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_TIMETABLE_FAILURE).performScrollTo().assertIsDisplayed()

        assertEquals(listOf<String?>("m-2"), chosen)
        assertEquals(listOf<String?>("c-2"), swaps)
    }

    @Test
    fun `a room can be stopped and an archived one resumed`() {
        val archived = mutableListOf<Pair<String, Boolean>>()
        compose.setContent {
            RoomsScreen(
                state =
                    RoomsUiState(
                        rooms = listOf(RoomDto("r-1", "Room A"), RoomDto("r-2", "Old", archived = true)),
                        loading = false,
                    ),
                actions = RoomsActions(onArchive = { id, value -> archived += id to value }),
            )
        }

        compose.onNodeWithTag(roomArchiveTag("r-1")).performClick()
        compose.onNodeWithTag(roomArchiveTag("r-2")).performClick()

        assertEquals(listOf("r-1" to true, "r-2" to false), archived)
    }
}
