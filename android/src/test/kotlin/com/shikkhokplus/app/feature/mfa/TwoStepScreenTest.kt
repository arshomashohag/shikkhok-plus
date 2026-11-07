package com.shikkhokplus.app.feature.mfa

import android.content.ClipboardManager
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.designsystem.TAG_OTP_FIELD
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.mfa.ui.MfaOfferContent
import com.shikkhokplus.app.feature.mfa.ui.TAG_MFA_OFFER_LATER
import com.shikkhokplus.app.feature.mfa.ui.TAG_MFA_OFFER_TURN_ON
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_CODE
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_COPY_CODES
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_COPY_SECRET
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_ERROR
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_LOW
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_NEW_CODES
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_NO_APP
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_OPEN_APP
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_RECOMMENDED
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_RECOVERY
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_REQUIRED
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_RETRY
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_SAVED
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_SECRET
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_TOGGLE
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_TURN_OFF
import com.shikkhokplus.app.feature.mfa.ui.TAG_TWO_STEP_TURN_ON
import com.shikkhokplus.app.feature.mfa.ui.TwoStepActions
import com.shikkhokplus.app.feature.mfa.ui.TwoStepScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** The two-step verification screen and the offer, rendered [0028]. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TwoStepScreenTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private fun status(
        enabled: Boolean = false,
        left: Int = 0,
        recommended: Boolean = false,
        required: Boolean = false,
    ) = MfaStatus(
        enabled = enabled,
        enabledAt = if (enabled) "2026-11-06T04:00:00Z" else null,
        recoveryCodesLeft = left,
        showRecommended = recommended && !enabled,
        required = required,
        canTurnOff = enabled && !required,
        lowOnCodes = enabled && left <= 2,
    )

    private fun render(state: MfaUiState, actions: TwoStepActions = TwoStepActions()) {
        compose.setContent { ShikkhokTheme { TwoStepScreen(state, actions) } }
    }

    private fun loaded(status: MfaStatus, flow: MfaFlow = MfaFlow.None) =
        MfaUiState(MfaStatusUiState.Loaded(status), flow)

    private val confirming = MfaFlow.Confirming("JBSWY3DPEHPK3PXP", "JBSW Y3DP EHPK 3PXP", "otpauth://totp/x")

    private fun clipboardText(): String? =
        compose.activity.getSystemService(ClipboardManager::class.java).primaryClip?.getItemAt(0)?.text?.toString()

    @Test
    fun `off and recommended offers Turn on with the recommendation and no Turn off`() {
        var started = 0
        render(loaded(status(recommended = true)), TwoStepActions(onTurnOn = { started++ }))

        compose.onNodeWithText("Off").assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_RECOMMENDED).assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_TURN_OFF).assertDoesNotExist()
        compose.onNodeWithTag(TAG_TWO_STEP_NEW_CODES).assertDoesNotExist()
        compose.onNodeWithTag(TAG_TWO_STEP_TURN_ON).performScrollTo().performClick()
        assertEquals(1, started)
    }

    @Test
    fun `on shows the codes left, New recovery codes and Turn off`() {
        render(loaded(status(enabled = true, left = 7)))

        compose.onNodeWithText("On").assertExists()
        compose.onNodeWithText("7 recovery codes left").assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_NEW_CODES).performScrollTo().assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_TURN_OFF).performScrollTo().assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_LOW).assertDoesNotExist()
        compose.onNodeWithTag(TAG_TWO_STEP_TURN_ON).assertDoesNotExist()
    }

    @Test
    fun `required for an administrator is said, with no way to turn it off`() {
        render(loaded(status(enabled = true, left = 9, required = true)))

        compose.onNodeWithTag(TAG_TWO_STEP_REQUIRED).assertExists()
        compose.onNodeWithText("Required for your account").assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_TURN_OFF).assertDoesNotExist()
    }

    @Test
    fun `few recovery codes left is a warning`() {
        render(loaded(status(enabled = true, left = 1)))

        compose.onNodeWithTag(TAG_TWO_STEP_LOW).performScrollTo().assertExists()
        compose.onNodeWithText("1 recovery code left").assertExists()
    }

    @Test
    fun `a failed status read offers a retry when the server allows one`() {
        var retried = 0
        render(
            MfaUiState(MfaStatusUiState.Failed("error.network.unreachable", retryable = true)),
            TwoStepActions(onRetry = { retried++ }),
        )

        compose.onNodeWithText("Try again").performClick()
        assertEquals(1, retried)
    }

    @Test
    fun `setup shows the key in fours, opens the app, and copies the key as sent`() {
        val opened = mutableListOf<String>()
        render(loaded(status(), confirming), TwoStepActions(onOpenAuthenticator = { opened += it }))

        compose.onNodeWithTag(TAG_TWO_STEP_SECRET).assertExists()
        compose.onNodeWithText("JBSW Y3DP EHPK 3PXP").assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_OPEN_APP).performClick()
        compose.onNodeWithTag(TAG_TWO_STEP_COPY_SECRET).performClick()

        assertEquals(listOf("otpauth://totp/x"), opened)
        assertEquals("JBSWY3DPEHPK3PXP", clipboardText())
        compose.onNodeWithTag(TAG_TWO_STEP_NO_APP).assertDoesNotExist()
    }

    @Test
    fun `no authenticator app is said, with the key still there to type`() {
        render(loaded(status(), confirming.copy(noAuthenticator = true)))

        compose.onNodeWithTag(TAG_TWO_STEP_NO_APP).assertExists()
        compose.onNodeWithText("No authenticator app found", substring = true).assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_SECRET).assertExists()
    }

    @Test
    fun `the sixth digit of the first code sends it`() {
        val typed = mutableListOf<String>()
        var confirmed = 0
        render(
            loaded(status(), confirming),
            TwoStepActions(onType = { typed += it }, onConfirm = { confirmed++ }),
        )

        compose.onNodeWithTag(TAG_OTP_FIELD).performTextInput("123456")

        assertEquals("123456", typed.last())
        assertEquals(1, confirmed)
    }

    @Test
    fun `a wrong first code shows the server's words, and no retry when it would not help`() {
        render(loaded(status(), confirming.copy(code = "000000", write = WriteState.Failed("mfa.code_wrong", false))))

        compose.onNodeWithTag(TAG_TWO_STEP_ERROR).performScrollTo().assertExists()
        compose.onNodeWithText("That code isn't right", substring = true).assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_RETRY).assertDoesNotExist()
    }

    @Test
    fun `a lost connection offers the retry, which sends again`() {
        var confirmed = 0
        render(
            loaded(
                status(),
                confirming.copy(code = "123456", write = WriteState.Failed("error.network.unreachable", true)),
            ),
            TwoStepActions(onConfirm = { confirmed++ }),
        )

        compose.onNodeWithTag(TAG_TWO_STEP_RETRY).performScrollTo().performClick()
        assertEquals(1, confirmed)
    }

    @Test
    fun `recovery codes are shown once, on a secure window, with Copy all`() {
        var saved = 0
        val codes = List(10) { "CODE$it-XXXXX" }
        render(
            loaded(status(enabled = true, left = 10), MfaFlow.Codes(codes, false)),
            TwoStepActions(onFinishCodes = { saved++ }),
        )

        compose.onAllNodesWithTag(TAG_TWO_STEP_CODE).assertCountEquals(10)
        compose.onNodeWithText("They won't be shown again.").assertExists()
        val flags = compose.activity.window.attributes.flags
        assertTrue(flags and WindowManager.LayoutParams.FLAG_SECURE != 0, "FLAG_SECURE while codes show")

        compose.onNodeWithTag(TAG_TWO_STEP_COPY_CODES).performScrollTo().performClick()
        assertEquals(codes.joinToString("\n"), clipboardText())

        compose.onNodeWithTag(TAG_TWO_STEP_SAVED).performScrollTo().performClick()
        assertEquals(1, saved)
    }

    @Test
    fun `the secure window is lifted once the codes are gone`() {
        var state by mutableStateOf(
            loaded(status(enabled = true, left = 10), MfaFlow.Codes(listOf("A"), renewed = true)),
        )
        compose.setContent { ShikkhokTheme { TwoStepScreen(state, TwoStepActions()) } }
        compose.onNodeWithText("Your old recovery codes no longer work.").assertExists()

        state = loaded(status(enabled = true, left = 10))
        compose.waitForIdle()

        assertEquals(0, compose.activity.window.attributes.flags and WindowManager.LayoutParams.FLAG_SECURE)
    }

    @Test
    fun `turning off by recovery code waits for a whole code`() {
        var turnedOff = 0
        render(
            loaded(status(enabled = true, left = 3), MfaFlow.TurningOff(useRecovery = true, input = "ABCDE")),
            TwoStepActions(onTurnOff = { turnedOff++ }),
        )

        compose.onNodeWithTag(TAG_TWO_STEP_RECOVERY).assertExists()
        compose.onNodeWithTag(TAG_TWO_STEP_TURN_OFF).assertIsNotEnabled()
        compose.onNodeWithTag(TAG_TWO_STEP_TOGGLE).assertExists()
        assertEquals(0, turnedOff)
    }

    @Test
    fun `a whole recovery code can be sent`() {
        var turnedOff = 0
        render(
            loaded(status(enabled = true, left = 3), MfaFlow.TurningOff(useRecovery = true, input = "ABCDE-FGHJK")),
            TwoStepActions(onTurnOff = { turnedOff++ }),
        )

        compose.onNodeWithTag(TAG_TWO_STEP_TURN_OFF).assertIsEnabled().performClick()
        assertEquals(1, turnedOff)
    }

    @Test
    fun `turning off by app code switches to a recovery code on request`() {
        var toggled = 0
        render(
            loaded(status(enabled = true, left = 3), MfaFlow.TurningOff()),
            TwoStepActions(onToggleRecovery = { toggled++ }),
        )

        compose.onNodeWithTag(TAG_OTP_FIELD).assertExists()
        compose.onNodeWithText("Use a recovery code instead").performScrollTo().performClick()
        assertEquals(1, toggled)
    }

    @Test
    fun `new recovery codes ask for an app code`() {
        var renewed = 0
        render(loaded(status(enabled = true, left = 1), MfaFlow.Renewing()), TwoStepActions(onRenew = { renewed++ }))

        compose.onNodeWithText("Your old recovery codes will stop working", substring = true).assertExists()
        compose.onNodeWithTag(TAG_OTP_FIELD).performTextInput("123456")
        assertEquals(1, renewed)
    }

    @Test
    fun `the offer turns on or puts it off`() {
        var on = 0
        var later = 0
        compose.setContent { ShikkhokTheme { MfaOfferContent(onTurnOn = { on++ }, onNotNow = { later++ }) } }

        compose.onNodeWithText("Protect your account with two-step verification").assertExists()
        compose.onNodeWithText("fee and student records", substring = true).assertExists()
        compose.onNodeWithTag(TAG_MFA_OFFER_TURN_ON).performClick()
        compose.onNodeWithTag(TAG_MFA_OFFER_LATER).performClick()

        assertEquals(1, on)
        assertEquals(1, later)
    }
}
