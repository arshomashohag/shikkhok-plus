package com.shikkhokplus.app.navigation

import androidx.compose.foundation.layout.Column
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.semantics.SemanticsActions
import com.shikkhokplus.app.feature.classcalendar.ui.TAG_PLAN_SAVE
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.activity.ComponentActivity
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import com.shikkhokplus.app.core.designsystem.TAG_SCAFFOLD_BACK
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.MonthViewDto
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.queue.TestQueueCipher
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.batchdetail.ui.ClassesTab
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarRepository
import com.shikkhokplus.app.feature.classcalendar.ClassCalendarViewModel
import com.shikkhokplus.app.feature.classcalendar.TopicWriter
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.feature.classcalendar.ui.TAG_PLAN_TOPIC
import com.shikkhokplus.app.feature.attendance.ui.TAG_CONFLICT_DISCARD
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

/**
 * The calendar and the class screens it opens, hosted together: tapping an
 * upcoming class shows the plan screen and leaves it there, and both the
 * back arrow and system Back return to the calendar.
 */
@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ClassScreensHostTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    @get:Rule
    val folder = TemporaryFolder()

    @Before
    fun setUp() = Dispatchers.setMain(UnconfinedTestDispatcher())

    @After
    fun tearDown() = Dispatchers.resetMain()

    private val day = "calendar_day_upcoming_2026-11-16"

    private val month =
        MonthViewDto(
            2026,
            11,
            "2026-09",
            "2026-12",
            days =
                listOf(
                    com.shikkhokplus.app.core.network.CalendarDayDto(
                        "2026-11-16",
                        "upcoming",
                        listOf(
                            com.shikkhokplus.app.core.network.CalendarClassDto(
                                sessionId = "s-1",
                                date = "2026-11-16",
                                startTime = "16:00:00",
                                state = "upcoming",
                                plannable = true,
                            ),
                        ),
                    ),
                ),
        )

    private val calendarRepo =
        object : ClassCalendarRepository {
            override suspend fun month(batchId: String, year: Int, month: Int) =
                AuthResult.Ok(this@ClassScreensHostTest.month)
        }

    private fun host(queue: QueueStore): ClassCalendarViewModel {
        val engine =
            MockEngine { request ->
                val headers = headersOf("Content-Type", listOf(ContentType.Application.Json.toString()))
                if (request.method == io.ktor.http.HttpMethod.Put) {
                    return@MockEngine respond(
                        """{"error":{"code":"TOPIC_CLASS_STARTED","retryable":false,""" +
                            """"message_key":"teaching.topic.class_started"}}""",
                        HttpStatusCode.Conflict,
                        headers,
                    )
                }
                val body =
                    if (request.url.encodedPath.endsWith("/attendance")) {
                        """{"seats":[],"attendance_version":0,"writable":true}"""
                    } else {
                        """{"session_id":"s-1","date":"2026-11-16","start_time":"16:00:00",""" +
                            """"origin":"recurrence","status":"scheduled","topic_version":2,"attendance_version":0}"""
                    }
                respond(body, HttpStatusCode.OK, headers)
            }
        val client = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())
        val calendar = ClassCalendarViewModel(calendarRepo, currentMonth = { YearMonth(2026, 11) })
        calendar.load("b-1")
        compose.setContent {
            ShikkhokTheme {
                val state by calendar.state.collectAsState()
                Column {
                    ClassesTab(state, null, calendar::pick, calendar::tapDay, calendar::retry)
                    ClassScreensHost(client, queue, calendar)
                }
            }
        }
        return calendar
    }

    private fun queue() = QueueStore(File(folder.root, QueueStore.FILE_NAME), TestQueueCipher)

    private fun open() {
        compose.waitUntil(5_000) { compose.onAllNodesWithTag(day).fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag(day).performClick()
        compose.waitForIdle()
    }

    @Test
    fun `tapping an upcoming class shows the plan screen and it stays`() {
        host(queue())

        open()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag(TAG_PLAN_TOPIC).fetchSemanticsNodes().isNotEmpty() }
        compose.mainClock.advanceTimeBy(1_000)
        compose.waitForIdle()

        compose.onAllNodesWithTag(TAG_PLAN_TOPIC).assertCountEquals(1)
    }

    @Test
    fun `the back arrow returns to the calendar`() {
        host(queue())
        open()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag(TAG_SCAFFOLD_BACK).fetchSemanticsNodes().isNotEmpty() }

        compose.onNodeWithTag(TAG_SCAFFOLD_BACK).performClick()
        compose.waitForIdle()

        compose.onAllNodesWithTag(TAG_PLAN_TOPIC).assertCountEquals(0)
        compose.onAllNodesWithTag(day).assertCountEquals(1)
    }

    @Test
    fun `system Back returns to the calendar, and the class opens again afterwards`() {
        host(queue())
        open()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag(TAG_PLAN_TOPIC).fetchSemanticsNodes().isNotEmpty() }

        compose.activityRule.scenario.onActivity { it.onBackPressedDispatcher.onBackPressed() }
        compose.waitForIdle()
        compose.onAllNodesWithTag(TAG_PLAN_TOPIC).assertCountEquals(0)

        open()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag(TAG_PLAN_TOPIC).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodesWithTag(TAG_PLAN_TOPIC).assertCountEquals(1)
    }

    @Test
    fun `a plan refused on save can be discarded, and the class then opens again`() {
        host(queue())
        open()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag(TAG_PLAN_SAVE).fetchSemanticsNodes().isNotEmpty() }
        compose.waitUntil(5_000) { runCatching { compose.onNodeWithTag(TAG_PLAN_SAVE).assertIsEnabled() }.isSuccess }
        compose.onNodeWithTag(TAG_PLAN_SAVE).performSemanticsAction(SemanticsActions.OnClick)
        compose.waitUntil(5_000) { compose.onAllNodesWithTag(TAG_CONFLICT_DISCARD).fetchSemanticsNodes().isNotEmpty() }

        compose.onNodeWithTag(TAG_CONFLICT_DISCARD).performSemanticsAction(SemanticsActions.OnClick)
        compose.waitForIdle()
        compose.onAllNodesWithTag(TAG_CONFLICT_DISCARD).assertCountEquals(0)
        compose.onAllNodesWithTag(TAG_PLAN_TOPIC).assertCountEquals(0)

        open()
        compose.waitUntil(5_000) { compose.onAllNodesWithTag(TAG_PLAN_TOPIC).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodesWithTag(TAG_PLAN_TOPIC).assertCountEquals(1)
        compose.onAllNodesWithTag(TAG_CONFLICT_DISCARD).assertCountEquals(0)
    }
}
