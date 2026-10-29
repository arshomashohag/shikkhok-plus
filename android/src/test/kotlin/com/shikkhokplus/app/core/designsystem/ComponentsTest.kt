package com.shikkhokplus.app.core.designsystem

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The shared components, rendered: what each one promises a screen.
 *
 * These are the pieces every screen is rebuilt on, so a regression here
 * is a regression everywhere: a disabled main action that still fires,
 * a refused field that does not say so to a screen reader, a retry that
 * calls nothing.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ComponentsTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun `a disabled main action cannot be pressed`() {
        var pressed = 0
        compose.setContent {
            ShikkhokTheme {
                Column {
                    PrimaryButton("Send code", { pressed++ }, enabled = false)
                    SecondaryButton("Try again", { pressed++ })
                }
            }
        }

        compose.onNodeWithText("Send code").assertIsNotEnabled().performClick()
        compose.onNodeWithText("Try again").assertIsEnabled().performClick()

        assertEquals(1, pressed)
    }

    @Test
    fun `every button kind reports its press`() {
        val pressed = mutableListOf<String>()
        compose.setContent {
            ShikkhokTheme {
                Column {
                    PrimaryButton("Approve", { pressed += "primary" })
                    TonalButton("Partial", { pressed += "tonal" })
                    DestructiveButton("Reject", { pressed += "outlined" })
                    DestructiveButton("Delete", { pressed += "filled" }, filled = true)
                    TextAction("See all", { pressed += "text" })
                }
            }
        }

        listOf("Approve", "Partial", "Reject", "Delete", "See all").forEach {
            compose.onNodeWithText(it).performClick()
        }

        assertEquals(listOf("primary", "tonal", "outlined", "filled", "text"), pressed)
    }

    @Test
    fun `a phone field shows the country code and passes what is typed`() {
        compose.setContent {
            ShikkhokTheme {
                var typed by remember { mutableStateOf("") }
                PhoneField(typed, { typed = it }, "Mobile number", help = "This is your login.")
            }
        }

        compose.onNodeWithText(PHONE_PREFIX).assertExists()
        compose.onNodeWithText(PHONE_PLACEHOLDER).assertExists()
        compose.onNodeWithText("This is your login.").assertExists()
        compose.onNodeWithContentDescription("Mobile number").performTextInput("01712345678")
        compose.onNodeWithText("01712345678").assertExists()
    }

    @Test
    fun `a refused field says so to a screen reader, not only in red`() {
        compose.setContent {
            ShikkhokTheme {
                ShikkhokTextField("", {}, "Full name", error = "Add your name", help = "Hidden by the error")
            }
        }

        compose
            .onNodeWithContentDescription("Full name")
            .assert(SemanticsMatcher.expectValue(SemanticsProperties.Error, "Add your name"))
        compose.onNodeWithText("Add your name").assertExists()
        compose.onNodeWithText("Hidden by the error").assertDoesNotExist()
    }

    @Test
    fun `an error card retries only when given a retry`() {
        var retried = 0
        compose.setContent {
            ShikkhokTheme {
                Column {
                    ErrorCard(
                        "Couldn't load",
                        "Check the connection.",
                        retryLabel = "Try again",
                        onRetry = { retried++ },
                    )
                    ErrorCard("Not available", null)
                }
            }
        }

        compose.onNodeWithTag(TAG_ERROR_RETRY).performClick()
        compose.onNodeWithText("Not available").assertExists()

        assertEquals(1, retried)
    }

    @Test
    fun `banners, empty states and skeletons render their content`() {
        compose.setContent {
            ShikkhokTheme {
                Column {
                    Banner("You've been added already", body = "Check your details.")
                    Banner("This number already has an account.", tone = BannerTone.ERROR)
                    Banner("Offline", tone = BannerTone.NEUTRAL, action = { TextAction("Retry", {}) })
                    EmptyState("No batches yet", "Create your first batch.", action = { PrimaryButton("Create", {}) })
                    SkeletonList(rows = 2)
                }
            }
        }

        compose.onNodeWithText("Check your details.").assertExists()
        compose.onNodeWithText("This number already has an account.").assertExists()
        compose.onNodeWithText("Retry").assertExists()
        compose.onNodeWithText("Create").assertExists()
        compose.onNodeWithTag(TAG_SKELETON).assertExists()
    }

    @Test
    fun `a compact chip names its state for a screen reader`() {
        compose.setContent {
            ShikkhokTheme {
                Column {
                    PaymentStateChip(PaymentState.VERIFYING, "Verifying", compact = true)
                    PaymentStateChip(PaymentState.OVERDUE, "68 days")
                }
            }
        }

        compose.onNodeWithText("Verifying").assertExists()
        compose.onNodeWithText("68 days").assertExists()
    }

    @Test
    fun `a pushed screen's back arrow and subtitle are in the bar`() {
        var back = 0
        compose.setContent {
            ShikkhokTheme {
                ListScreenScaffold(title = "Physics A", subtitle = "18 students", onBack = { back++ }) {}
            }
        }

        compose.onNodeWithText("18 students").assertExists()
        compose.onNodeWithTag(TAG_SCAFFOLD_BACK).performClick()

        assertEquals(1, back)
    }
}
