package com.shikkhokplus.app.feature.marks

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.ui.TAG_FORM_NAME
import com.shikkhokplus.app.core.ui.TAG_FORM_SUBMIT
import com.shikkhokplus.app.feature.marks.ui.ExamCreateForm
import com.shikkhokplus.app.feature.marks.ui.TAG_EXAM_SUBJECT
import com.shikkhokplus.app.feature.marks.ui.TAG_EXAM_SUBJECTS_FAILED
import com.shikkhokplus.app.feature.marks.ui.TAG_EXAM_TOTAL
import com.shikkhokplus.app.feature.marks.ui.isoDate
import com.shikkhokplus.app.feature.marks.ui.todayAsUtcMillis
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The create-exam form: the screen that was missing entirely, because
 * the exam list's create button was never wired and no response
 * carried the subject key an exam needs.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ExamCreateFormTest {

    @get:Rule
    val compose = createComposeRule()

    /** 4 Nov 2026, 00:00 UTC, as the date picker reports it. */
    private val nov4 = 1_793_750_400_000L

    private val physics = SubjectOptionDto(id = "bs-1", name = "Physics")
    private val chemistry = SubjectOptionDto(id = "bs-2", name = "Chemistry")

    @Test
    fun `a filled form sends the ISO date, the total and the subject key`() {
        var sent: List<Any>? = null
        compose.setContent {
            ExamCreateForm(
                subjects = listOf(physics),
                onCreate = { t, d, n, s -> sent = listOf(t, d, n, s) },
                onCancel = {},
                todayUtcMillis = nov4,
            )
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Weekly test 5")
        compose.onNodeWithTag(TAG_EXAM_TOTAL).performTextInput("50")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        // One subject is pre-selected: there is nothing to choose.
        assertEquals(listOf("Weekly test 5", "2026-11-04", 50, "bs-1"), sent)
    }

    @Test
    fun `with several subjects nothing is chosen for the teacher`() {
        compose.setContent {
            ExamCreateForm(
                subjects = listOf(physics, chemistry),
                onCreate = { _, _, _, _ -> },
                onCancel = {},
                todayUtcMillis = nov4,
            )
        }
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Monthly")
        compose.onNodeWithTag(TAG_EXAM_TOTAL).performTextInput("100")

        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsNotEnabled()

        compose.onAllNodesWithTag(TAG_EXAM_SUBJECT)[1].performClick()
        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsEnabled()
    }

    @Test
    fun `a total of zero cannot be submitted`() {
        // The server requires at least one [BR4.1].
        compose.setContent {
            ExamCreateForm(
                subjects = listOf(physics),
                onCreate = { _, _, _, _ -> },
                onCancel = {},
                todayUtcMillis = nov4,
            )
        }
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Quiz")
        compose.onNodeWithTag(TAG_EXAM_TOTAL).performTextInput("0")

        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `no subjects reads as a failure, never as nothing to choose`() {
        // A batch always has a subject [AC2.1.1], so empty is a failed read.
        compose.setContent {
            ExamCreateForm(
                subjects = emptyList(),
                onCreate = { _, _, _, _ -> },
                onCancel = {},
                todayUtcMillis = nov4,
            )
        }

        compose.onNodeWithTag(TAG_EXAM_SUBJECTS_FAILED).assertIsDisplayed()
        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `while saving the form cannot submit again`() {
        var calls = 0
        compose.setContent {
            ExamCreateForm(
                subjects = listOf(physics),
                onCreate = { _, _, _, _ -> calls++ },
                onCancel = {},
                saving = true,
                todayUtcMillis = nov4,
            )
        }
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Quiz")
        compose.onNodeWithTag(TAG_EXAM_TOTAL).performTextInput("20")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertEquals(0, calls)
    }

    @Test
    fun `a picked date is formatted in UTC, not shifted by the phone's zone`() {
        // **Run west of UTC on purpose.** The picker reports UTC midnight.
        // Formatted in local time that reads correctly east of UTC --
        // Bangladesh included, so a test run there would pass whatever
        // the code did -- and shows the PREVIOUS day west of it. Los
        // Angeles is where a local-time formatter fails.
        val saved = TimeZone.getDefault()
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("America/Los_Angeles"))
            assertEquals("2026-11-04", isoDate(nov4))
        } finally {
            TimeZone.setDefault(saved)
        }
    }

    @Test
    fun `today is the local calendar date, even before 6 am in Dhaka`() {
        // Today must be the LOCAL date expressed as UTC midnight, or a
        // teacher at UTC+6 opening the form before 6 am would get
        // yesterday as the default.
        val saved = TimeZone.getDefault()
        try {
            TimeZone.setDefault(TimeZone.getTimeZone("Asia/Dhaka"))
            val localToday =
                SimpleDateFormat("yyyy-MM-dd", Locale.ENGLISH).format(Date())
            assertEquals(localToday, isoDate(todayAsUtcMillis()))
        } finally {
            TimeZone.setDefault(saved)
        }
    }

    @Test
    fun `nothing is sent until the teacher submits`() {
        var sent: String? = null
        compose.setContent {
            ExamCreateForm(
                subjects = listOf(physics),
                onCreate = { t, _, _, _ -> sent = t },
                onCancel = {},
                todayUtcMillis = nov4,
            )
        }
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Quiz")

        assertNull(sent)
    }
}
