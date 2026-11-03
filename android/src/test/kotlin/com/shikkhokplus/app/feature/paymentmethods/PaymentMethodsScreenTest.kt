package com.shikkhokplus.app.feature.paymentmethods

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.feature.paymentmethods.ui.MethodEditorScreen
import com.shikkhokplus.app.feature.paymentmethods.ui.PaymentMethodsScreen
import com.shikkhokplus.app.feature.paymentmethods.ui.TAG_EDITOR_SAVE
import com.shikkhokplus.app.feature.paymentmethods.ui.TAG_METHODS_ADD_BANK
import com.shikkhokplus.app.feature.paymentmethods.ui.TAG_METHODS_EMPTY
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** P1 and P3, rendered. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PaymentMethodsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `the list shows each method and the two add actions`() {
        val rows =
            listOf(
                MethodRow("m1", MethodKind.MOBILE, "bKash", "01712345678", null, null),
                MethodRow("b1", MethodKind.BANK, "Dutch-Bangla Bank", "Rahima Akter · ••• 4521", "Mirpur branch", null),
            )
        var bank = 0
        compose.setContent {
            PaymentMethodsScreen(
                state = PaymentMethodsUiState.Loaded(rows),
                onAddMobile = {},
                onAddBank = { bank++ },
                onEdit = {},
                onRemove = {},
                onRetry = {},
                onBack = {},
            )
        }

        compose.onNodeWithText("bKash").assertIsDisplayed()
        compose.onNodeWithText("Mirpur branch").assertIsDisplayed()
        compose.onNodeWithTag(TAG_METHODS_ADD_BANK).performScrollTo().performClick()
        assertEquals(1, bank)
    }

    @Test
    fun `an empty list says so and still offers to add`() {
        compose.setContent {
            PaymentMethodsScreen(
                state = PaymentMethodsUiState.Empty,
                onAddMobile = {},
                onAddBank = {},
                onEdit = {},
                onRemove = {},
                onRetry = {},
                onBack = {},
            )
        }

        compose.onNodeWithTag(TAG_METHODS_EMPTY).assertIsDisplayed()
    }

    private fun editor(state: MethodEditorState) {
        compose.setContent {
            MethodEditorScreen(
                state = state,
                options = emptyList(),
                onKind = {},
                onProvider = {},
                onMobile = {},
                onAccountNumber = {},
                onAccountName = {},
                onBranch = {},
                onNote = {},
                onSave = {},
                onRetry = {},
                onBack = {},
            )
        }
    }

    @Test
    fun `save is disabled on an incomplete bank form`() {
        editor(MethodEditorState(kind = MethodKind.BANK, accountNumber = "123"))
        compose.onNodeWithTag(TAG_EDITOR_SAVE).performScrollTo().assertIsNotEnabled()
    }

    @Test
    fun `save is enabled on a complete bank form`() {
        editor(
            MethodEditorState(
                kind = MethodKind.BANK,
                provider = "DBBL",
                accountNumber = "123",
                accountName = "Rahima",
                branchName = "Mirpur",
            ),
        )
        compose.onNodeWithTag(TAG_EDITOR_SAVE).performScrollTo().assertIsEnabled()
    }
}
