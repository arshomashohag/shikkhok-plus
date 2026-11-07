package com.shikkhokplus.app.feature.payroll

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.SalaryLineDto
import com.shikkhokplus.app.feature.myexams.Loadable
import com.shikkhokplus.app.feature.payroll.ui.MyPayScreen
import com.shikkhokplus.app.feature.payroll.ui.PayrollActions
import com.shikkhokplus.app.feature.payroll.ui.PayrollScreen
import com.shikkhokplus.app.feature.payroll.ui.payrollAdjustTag
import com.shikkhokplus.app.feature.payroll.ui.payrollApproveTag
import com.shikkhokplus.app.feature.payroll.ui.payrollPayTag
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** The payroll and My pay, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PayrollScreensTest {

    @get:Rule
    val compose = createComposeRule()

    private fun line(id: String, status: String, remaining: String = "5000.00") =
        SalaryLineDto(
            lineId = id,
            staffId = "s-1",
            staffName = "Karim",
            centreName = "Alo Coaching",
            period = "2026-10",
            basis = "per_class",
            rate = Money.of("500.00"),
            classesHeld = 10,
            base = Money.of("5000.00"),
            owed = Money.of("5000.00"),
            paid = Money.of("0.00"),
            remaining = Money.of(remaining),
            status = status,
        )

    @Test
    fun `a draft offers adjust and approve, an approved line offers pay`() {
        val approved = mutableListOf<String>()
        val paying = mutableListOf<String>()
        compose.setContent {
            PayrollScreen(
                state =
                    PayrollUiState(
                        month = "2026-10",
                        lines = Loadable.Loaded(listOf(line("l-1", "draft"), line("l-2", "approved"))),
                    ),
                actions = PayrollActions(onApprove = { approved += it }, onOpenPay = { paying += it }),
            )
        }
        compose.onNodeWithTag(payrollAdjustTag("l-1")).assertIsDisplayed()
        compose.onNodeWithTag(payrollApproveTag("l-1")).performClick()
        compose.onNodeWithTag(payrollPayTag("l-2")).performScrollTo().performClick()
        compose.onNodeWithTag(payrollApproveTag("l-2")).assertDoesNotExist()
        assertEquals(listOf("l-1"), approved)
        assertEquals(listOf("l-2"), paying)
    }

    @Test
    fun `a fully paid line offers nothing, and my pay names the month and centre`() {
        compose.setContent {
            MyPayScreen(state = Loadable.Loaded(listOf(line("l-3", "approved", remaining = "0.00"))), onRetry = {})
        }
        compose.onNodeWithText("Alo Coaching", substring = true).assertIsDisplayed()
        compose.onNodeWithTag(payrollPayTag("l-3")).assertDoesNotExist()
    }
}
