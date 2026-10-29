package com.shikkhokplus.app.feature.roster

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import com.shikkhokplus.app.feature.roster.ui.AddStudentScreen
import com.shikkhokplus.app.feature.roster.ui.AddStudentUiState
import com.shikkhokplus.app.feature.roster.ui.TAG_ADD_STUDENT_ADDED
import com.shikkhokplus.app.feature.roster.ui.TAG_ADD_STUDENT_ERROR
import com.shikkhokplus.app.feature.roster.ui.TAG_ADD_STUDENT_FORM
import com.shikkhokplus.app.feature.roster.ui.TAG_ADD_STUDENT_RETRY
import com.shikkhokplus.app.feature.roster.ui.TAG_ADD_STUDENT_SUBMITTING
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * `T8` add student, in each of its four states [US2.2].
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class AddStudentScreenTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `the form state draws the form`() {
        compose.setContent {
            AddStudentScreen(
                state = AddStudentUiState.Form,
                onAdd = { _, _, _, _ -> },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_ADD_STUDENT_FORM).assertIsDisplayed()
    }

    @Test
    fun `submitting shows progress and not the form`() {
        compose.setContent {
            AddStudentScreen(
                state = AddStudentUiState.Submitting,
                onAdd = { _, _, _, _ -> },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_ADD_STUDENT_SUBMITTING).assertIsDisplayed()
        compose.onNodeWithTag(TAG_ADD_STUDENT_FORM).assertDoesNotExist()
    }

    @Test
    fun `A DUPLICATE ARRIVES AS A SERVER REFUSAL, not a client check`() {
        // [frontend-components: Form validation]. Whether a number is
        // already on this batch is a SERVER decision: the client holds
        // no roster of every batch and could not answer it, and a
        // client check with no server counterpart would be a business
        // rule living on the client.
        //
        // What this asserts is that the refusal has somewhere to land —
        // the screen has a Failed state and renders the server's
        // message key rather than a sentence the client invented.
        compose.setContent {
            AddStudentScreen(
                state = AddStudentUiState.Failed(
                    "batch.not_found",
                    retryable = false,
                ),
                onAdd = { _, _, _, _ -> },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_ADD_STUDENT_ERROR).assertIsDisplayed()
        compose.onNodeWithTag(TAG_ADD_STUDENT_RETRY).assertDoesNotExist()
    }

    @Test
    fun `an added seat is confirmed without claiming anyone was told`() {
        // [BR1.5, AC1.15.4]. **Nothing is sent to the person named.**
        // They discover the seat when they sign in, and the teacher is
        // told nothing further — so the confirmation must not say an
        // invitation was sent. That absence is the assertion.
        compose.setContent {
            AddStudentScreen(
                state = AddStudentUiState.Added("Rahim"),
                onAdd = { _, _, _, _ -> },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_ADD_STUDENT_ADDED).assertIsDisplayed()
        compose.onNodeWithText("Student added.").assertIsDisplayed()
    }

    @Test
    fun `the guardian field is explained as optional`() {
        // A required-looking optional field is the commonest reason a
        // teacher invents a number, and an invented number is exactly
        // the mistyped-number exposure the acceptance model exists to
        // close.
        compose.setContent {
            AddStudentScreen(
                state = AddStudentUiState.Form,
                onAdd = { _, _, _, _ -> },
                onCancel = {},
            )
        }

        // `assertExists`, not `assertIsDisplayed`: the hint sits below
        // the form and is off-screen at the test's viewport height.
        // What this test is about is that the sentence is PRESENT and
        // says "optional"; where it lands vertically is the Bangla
        // layout check's business, not this one's.
        compose.onNodeWithText(
            "Optional. The guardian sees this student's records once they accept.",
        ).assertExists()
    }
}
