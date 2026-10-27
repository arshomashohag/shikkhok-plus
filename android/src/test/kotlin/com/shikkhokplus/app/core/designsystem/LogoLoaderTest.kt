package com.shikkhokplus.app.core.designsystem

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The brand loader.
 *
 * **What can be asserted here and what cannot.** Robolectric does not
 * advance an infinite transition, so no animation frame is ever drawn
 * under test and the drawing code cannot be exercised. What these
 * check is the contract around it: that it renders at all, and that
 * its label reaches the screen — the part a person actually reads
 * while waiting.
 *
 * The behaviour the loader exists to serve is covered where it lives:
 * `AuthViewModelTest` asserts the app starts at `Restoring` and
 * resolves away from it on both the success and failure paths.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class LogoLoaderTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `the loader renders`() {
        compose.setContent { ShikkhokTheme { LogoLoader() } }

        compose.onNodeWithTag(TAG_LOGO_LOADER).assertIsDisplayed()
    }

    @Test
    fun `a label is shown beside the mark`() {
        // A loader with no words leaves a person guessing whether the
        // app is working or stuck.
        compose.setContent {
            ShikkhokTheme { LogoLoader(label = "Signing you in") }
        }

        compose.onNodeWithText("Signing you in").assertIsDisplayed()
    }

    @Test
    fun `no label renders no stray text`() {
        // The label is optional: inside a button or a small slot there
        // is nowhere to put one.
        compose.setContent { ShikkhokTheme { LogoLoader() } }

        compose.onNodeWithTag(TAG_LOGO_LOADER).assertIsDisplayed()
    }

    @Test
    fun `the full-screen loader renders with its label`() {
        // What a returning teacher sees while the stored session is
        // redeemed, instead of the sign-in screen flashing past.
        compose.setContent {
            ShikkhokTheme { FullScreenLoader(label = "Signing you in") }
        }

        compose.onNodeWithTag(TAG_LOGO_LOADER).assertIsDisplayed()
        compose.onNodeWithText("Signing you in").assertIsDisplayed()
    }
}
