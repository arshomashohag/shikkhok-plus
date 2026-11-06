package com.shikkhokplus.app.feature.myclasses

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.network.ClassRosterDto
import com.shikkhokplus.app.core.network.MyClassDto
import com.shikkhokplus.app.core.network.RosterSeatDto
import com.shikkhokplus.app.feature.myclasses.ui.MyClassActions
import com.shikkhokplus.app.feature.myclasses.ui.MyClassScreen
import com.shikkhokplus.app.feature.myclasses.ui.MyClassesActions
import com.shikkhokplus.app.feature.myclasses.ui.MyClassesScreen
import com.shikkhokplus.app.feature.myclasses.ui.TAG_MY_CLASS_FAILURE
import com.shikkhokplus.app.feature.myclasses.ui.TAG_MY_CLASS_SAVE_ATTENDANCE
import com.shikkhokplus.app.feature.myclasses.ui.myClassTag
import com.shikkhokplus.app.feature.myclasses.ui.mySeatTag
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** A centre teacher's classes and one class, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MyClassesScreensTest {

    @get:Rule
    val compose = createComposeRule()

    private val roster =
        ClassRosterDto(
            seats = listOf(RosterSeatDto("e-1", "Rafi", true), RosterSeatDto("e-2", "Mitu", false)),
            attendanceVersion = 1,
            writable = true,
            topicVersion = 0,
        )

    @Test
    fun `a class names its centre and room, and tapping opens it`() {
        val opened = mutableListOf<String>()
        compose.setContent {
            MyClassesScreen(
                state =
                    MyClassesUiState(
                        weekStart = "2026-11-06",
                        body =
                            MyClassesBody.Loaded(
                                listOf(
                                    "2026-11-06" to
                                        listOf(
                                            MyClassDto(
                                                sessionId = "c-1",
                                                centreName = "Alo Coaching",
                                                batchName = "Physics",
                                                date = "2026-11-06",
                                                startTime = "16:00",
                                                status = "scheduled",
                                                roomName = "Room A",
                                            ),
                                        ),
                                ),
                            ),
                    ),
                actions = MyClassesActions(onOpen = { opened += it }),
            )
        }
        compose.onNodeWithText("Alo Coaching · Room A").assertIsDisplayed()
        compose.onNodeWithTag(myClassTag("c-1")).performClick()
        assertEquals(listOf("c-1"), opened)
    }

    @Test
    fun `a week with no classes says so`() {
        compose.setContent {
            MyClassesScreen(
                state = MyClassesUiState(weekStart = "2026-11-06", body = MyClassesBody.Loaded(emptyList())),
                actions = MyClassesActions(),
            )
        }
        compose.onNodeWithText("No classes assigned to you on these days.").assertIsDisplayed()
    }

    @Test
    fun `each seat toggles, and a refusal is shown above the roster`() {
        val toggled = mutableListOf<String>()
        compose.setContent {
            MyClassScreen(
                state =
                    MyClassUiState(
                        body = MyClassBody.Loaded(roster),
                        absent = setOf("e-2"),
                        failureKey = "class.reassigned",
                    ),
                actions = MyClassActions(onToggle = { toggled += it }),
            )
        }
        compose.onNodeWithTag(TAG_MY_CLASS_FAILURE).assertIsDisplayed()
        compose.onNodeWithTag(mySeatTag("e-2")).assertIsDisplayed()
        compose.onNodeWithText("Absent").assertIsDisplayed()
        compose.onNodeWithTag(mySeatTag("e-1")).performClick()
        assertEquals(listOf("e-1"), toggled)
        compose.onNodeWithTag(TAG_MY_CLASS_SAVE_ATTENDANCE).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `a closed class offers no save and says why`() {
        compose.setContent {
            MyClassScreen(
                state = MyClassUiState(body = MyClassBody.Loaded(roster.copy(writable = false))),
                actions = MyClassActions(),
            )
        }
        compose.onNodeWithTag(TAG_MY_CLASS_SAVE_ATTENDANCE).assertDoesNotExist()
        compose.onNodeWithText("This class can no longer be changed.").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(mySeatTag("e-1")).assertIsNotEnabled()
    }
}
