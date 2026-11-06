package com.shikkhokplus.app.feature.extrafees

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ExtraFeeStudentDto
import com.shikkhokplus.app.core.network.RecordPaymentBodyDto
import com.shikkhokplus.app.feature.extrafees.ui.ExtraFeeDetailScreen
import com.shikkhokplus.app.feature.extrafees.ui.ExtraFeesScreen
import com.shikkhokplus.app.feature.extrafees.ui.RaiseFeeActions
import com.shikkhokplus.app.feature.extrafees.ui.RaiseFeeScreen
import com.shikkhokplus.app.feature.extrafees.ui.TAG_EXTRA_FEES_EMPTY
import com.shikkhokplus.app.feature.extrafees.ui.TAG_RAISE_SUBMIT
import com.shikkhokplus.app.feature.extrafees.ui.extraFeeTag
import com.shikkhokplus.app.feature.extrafees.ui.feeRecordTag
import com.shikkhokplus.app.feature.extrafees.ui.seatChoiceTag
import com.shikkhokplus.app.feature.fees.RecordSheet
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The teacher's exam and other fee screens, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ExtraFeesScreensTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `the list shows each fee's server totals and opens one`() {
        val opened = mutableListOf<String>()
        compose.setContent {
            ExtraFeesScreen(
                state = ExtraFeesUiState.Loaded(listOf(ExtraFeesViewModelsTest.summary())),
                onOpen = { opened += it },
                onRaise = {},
                onRetry = {},
                onBack = {},
            )
        }

        compose.onNodeWithText("Half-yearly exam").assertIsDisplayed()
        compose.onNodeWithText("৳700 of ৳1,000 collected").assertIsDisplayed()
        compose.onNodeWithText("1 of 2 paid · 1 owe ৳300").assertIsDisplayed()
        compose.onNodeWithTag(extraFeeTag("f-1")).performClick()
        assertEquals(listOf("f-1"), opened)
    }

    @Test
    fun `an empty batch says so`() {
        compose.setContent {
            ExtraFeesScreen(ExtraFeesUiState.Loaded(emptyList()), onOpen = {}, onRaise = {}, onRetry = {}, onBack = {})
        }
        compose.onNodeWithTag(TAG_EXTRA_FEES_EMPTY).assertIsDisplayed()
    }

    @Test
    fun `each student can be charged, waived or left out, and the button counts who is reached`() {
        val chosen = mutableListOf<Pair<String, SeatChoice>>()
        compose.setContent {
            RaiseFeeScreen(
                state =
                    RaiseFeeUiState(
                        loading = false,
                        students = listOf(RaiseStudent("e-1", "Tanvir"), RaiseStudent("e-2", "Tania")),
                        label = "Exam",
                        typedAmount = "500",
                        dueOn = "2026-11-20",
                        choices = mapOf("e-2" to SeatChoice.LEAVE_OUT),
                    ),
                actions = RaiseFeeActions(onChoose = { id, choice -> chosen += id to choice }),
            )
        }

        compose.onNodeWithTag(seatChoiceTag("e-1", SeatChoice.WAIVE)).performScrollTo().performClick()
        compose.onNodeWithText("Raise for 1 students").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag(TAG_RAISE_SUBMIT).assertIsEnabled()
        assertEquals(listOf("e-1" to SeatChoice.WAIVE), chosen)
    }

    @Test
    fun `an unnamed fee cannot be raised`() {
        compose.setContent {
            RaiseFeeScreen(
                state =
                    RaiseFeeUiState(
                        loading = false,
                        students = listOf(RaiseStudent("e-1", "Tanvir")),
                        dueOn = "2026-11-20",
                    ),
                actions = RaiseFeeActions(),
            )
        }
        compose.onNodeWithTag(TAG_RAISE_SUBMIT).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `only a student who still owes offers record payment`() {
        val recording = mutableListOf<ExtraFeeStudentDto>()
        compose.setContent {
            ExtraFeeDetailScreen(
                state = ExtraFeeDetailUiState.Loaded(ExtraFeesViewModelsTest.detail()),
                recorded = false,
                onRecord = { recording += it },
                onRetry = {},
                onBack = {},
            )
        }

        compose.onNodeWithTag(feeRecordTag("e-1")).assertDoesNotExist()
        compose.onNodeWithTag(feeRecordTag("e-2")).performScrollTo().performClick()
        assertEquals(listOf("e-2"), recording.map { it.enrollmentId })
    }

    @Test
    fun `a record against a fee carries the fee and its purpose, and a monthly one neither`() {
        val forFee = RecordSheet.open(Money.of("300.00"), "k", extraFeeId = "f-1").body()
        val monthly = RecordSheet.open(Money.of("300.00"), "k").body()

        assertEquals("extra" to "f-1", forFee?.purpose to forFee?.extraFeeId)
        assertEquals(RecordPaymentBodyDto(amount = Money.of("300.00"), clientMutationId = "k"), monthly)
    }
}
