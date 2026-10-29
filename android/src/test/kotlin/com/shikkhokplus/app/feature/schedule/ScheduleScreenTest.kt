package com.shikkhokplus.app.feature.schedule

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.network.ScheduleSlotDto
import com.shikkhokplus.app.core.ui.TAG_SCHEDULE_DAY
import com.shikkhokplus.app.feature.schedule.ui.ScheduleScreen
import com.shikkhokplus.app.feature.schedule.ui.TAG_SCHEDULE_SAVE
import com.shikkhokplus.app.feature.sessions.ui.AddSessionDialog
import com.shikkhokplus.app.feature.sessions.ui.TAG_ADD_SESSION_CONFIRM
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The schedule screen, and the one-off class dialog beside it. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ScheduleScreenTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `an existing schedule loads and saves with a day added`() {
        var saved: List<ScheduleSlotDto>? = null
        compose.setContent {
            ScheduleScreen(
                stored = listOf(ScheduleSlotDto(0, "16:00", "17:00")),
                onSave = { saved = it },
                onBack = {},
            )
        }

        // Chips run Saturday first: index 0 is Saturday (5).
        compose.onAllNodesWithTag(TAG_SCHEDULE_DAY)[0].performScrollTo().performClick()
        compose.onNodeWithTag(TAG_SCHEDULE_SAVE).performScrollTo().performClick()

        assertEquals(listOf(5, 0), saved?.map { it.weekday })
        assertEquals(setOf("16:00"), saved?.map { it.startTime }?.toSet())
    }

    @Test
    fun `the screen says existing classes are left alone`() {
        // BR1.2: silence here would read as a promise the server does
        // not keep.
        compose.setContent {
            ScheduleScreen(stored = listOf(ScheduleSlotDto(0, "16:00", "17:00")), onSave = {}, onBack = {})
        }

        compose.onNodeWithText("Classes already listed stay as they are", substring = true)
            .performScrollTo()
            .assertIsDisplayed()
    }

    @Test
    fun `adding a class sends the picked date and time`() {
        var added: Pair<String, String>? = null
        compose.setContent {
            AddSessionDialog(
                onAdd = { date, start -> added = date to start },
                onDismiss = {},
                todayUtcMillis = 1_793_750_400_000L,
            )
        }

        compose.onNodeWithTag(TAG_ADD_SESSION_CONFIRM).performClick()

        assertEquals("2026-11-04" to "16:00", added)
    }
}
