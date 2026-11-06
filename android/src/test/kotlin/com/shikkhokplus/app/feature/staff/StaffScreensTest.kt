package com.shikkhokplus.app.feature.staff

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.feature.staff.ui.StaffFormActions
import com.shikkhokplus.app.feature.staff.ui.StaffFormScreen
import com.shikkhokplus.app.feature.staff.ui.StaffListActions
import com.shikkhokplus.app.feature.staff.ui.StaffListScreen
import com.shikkhokplus.app.feature.staff.ui.TAG_STAFF_LEAVE_CONFIRM
import com.shikkhokplus.app.feature.staff.ui.TAG_STAFF_PHONE
import com.shikkhokplus.app.feature.staff.ui.TAG_STAFF_RATE
import com.shikkhokplus.app.feature.staff.ui.TAG_STAFF_SAVE
import com.shikkhokplus.app.feature.staff.ui.staffLeaveTag
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The Teachers & staff console, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class StaffScreensTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `a record shows pay and app access, and leaving is confirmed`() {
        val left = mutableListOf<String>()
        val gone = StaffViewModelsTest.teacher().copy(staffId = "s-2", status = "left", leftOn = "2026-10-31")
        compose.setContent {
            StaffListScreen(
                state = StaffListUiState.Loaded(listOf(StaffViewModelsTest.teacher(), gone)),
                actions = StaffListActions(onLeave = { left += it }),
            )
        }

        compose.onAllNodesWithText("Teacher · ৳8,000 a month")[0].assertIsDisplayed()
        compose.onNodeWithText("Invited to the app").assertIsDisplayed()
        compose.onNodeWithText("Left on 31 Oct").assertIsDisplayed()
        compose.onNodeWithTag(staffLeaveTag("s-2")).assertDoesNotExist()
        compose.onNodeWithTag(staffLeaveTag("s-1")).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_STAFF_LEAVE_CONFIRM).performClick()

        assertEquals(listOf("s-1"), left)
    }

    @Test
    fun `an edited teacher's number cannot be changed and not paid hides the amount`() {
        compose.setContent {
            StaffFormScreen(
                state =
                    StaffFormUiState(
                        mode = StaffFormMode.Edit(StaffViewModelsTest.teacher()),
                        name = "Karim",
                        phone = "+8801811223344",
                        basis = PayBasis.NONE,
                    ),
                actions = StaffFormActions(),
            )
        }

        compose.onNodeWithTag(TAG_STAFF_PHONE).assertIsNotEnabled()
        compose.onNodeWithTag(TAG_STAFF_RATE).assertDoesNotExist()
    }

    @Test
    fun `a paid basis without an amount cannot be saved`() {
        compose.setContent {
            StaffFormScreen(
                state = StaffFormUiState(mode = StaffFormMode.AddOther, name = "Salma", basis = PayBasis.MONTHLY),
                actions = StaffFormActions(),
            )
        }

        compose.onNodeWithTag(TAG_STAFF_SAVE).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `a per-class rate reads as a class rate`() {
        compose.setContent {
            StaffListScreen(
                state =
                    StaffListUiState.Loaded(
                        listOf(
                            StaffViewModelsTest.teacher().copy(payBasis = "per_class", payRate = Money.of("500.00")),
                        ),
                    ),
                actions = StaffListActions(),
            )
        }

        compose.onNodeWithText("Teacher · ৳500 a class").assertIsDisplayed()
    }
}
