package com.shikkhokplus.app.feature.batches

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import com.shikkhokplus.app.feature.batches.ui.CreateBatchScreen
import com.shikkhokplus.app.feature.batches.ui.CreateBatchUiState
import com.shikkhokplus.app.feature.batches.ui.TAG_CREATE_BATCH_CREATED
import com.shikkhokplus.app.feature.batches.ui.TAG_CREATE_BATCH_ERROR
import com.shikkhokplus.app.feature.batches.ui.TAG_CREATE_BATCH_FORM
import com.shikkhokplus.app.feature.batches.ui.TAG_CREATE_BATCH_RETRY
import com.shikkhokplus.app.feature.batches.ui.TAG_CREATE_BATCH_SUBMITTING
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Creating a class, in each of its four states [US2.1].
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class CreateBatchScreenTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `the form state draws the form`() {
        compose.setContent {
            CreateBatchScreen(
                state = CreateBatchUiState.Form,
                onCreate = { _, _, _, _, _ -> },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_CREATE_BATCH_FORM).assertIsDisplayed()
    }

    @Test
    fun `submitting shows progress and not the form`() {
        // A form still on screen during submission invites a second
        // submit, and V1 has no local write queue to reconcile one
        // [TC-8, D-9].
        compose.setContent {
            CreateBatchScreen(
                state = CreateBatchUiState.Submitting,
                onCreate = { _, _, _, _, _ -> },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_CREATE_BATCH_SUBMITTING).assertIsDisplayed()
        compose.onNodeWithTag(TAG_CREATE_BATCH_FORM).assertDoesNotExist()
    }

    @Test
    fun `a refusal shows the server's message`() {
        compose.setContent {
            CreateBatchScreen(
                state = CreateBatchUiState.Failed(
                    "batch.create.subject_required",
                    retryable = false,
                ),
                onCreate = { _, _, _, _, _ -> },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_CREATE_BATCH_ERROR).assertIsDisplayed()
    }

    @Test
    fun `retry appears only when the server said retryable`() {
        // [TC-9]. A retry on a non-retryable refusal invites the
        // teacher to repeat something that cannot work — and "no
        // subject named" cannot be fixed by retrying.
        compose.setContent {
            CreateBatchScreen(
                state = CreateBatchUiState.Failed(
                    "batch.create.subject_required",
                    retryable = false,
                ),
                onCreate = { _, _, _, _, _ -> },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_CREATE_BATCH_RETRY).assertDoesNotExist()
    }

    @Test
    fun `a created class is confirmed`() {
        compose.setContent {
            CreateBatchScreen(
                state = CreateBatchUiState.Created("Physics"),
                onCreate = { _, _, _, _, _ -> },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_CREATE_BATCH_CREATED).assertIsDisplayed()
    }
}
