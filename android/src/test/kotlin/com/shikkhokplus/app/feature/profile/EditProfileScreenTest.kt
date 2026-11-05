package com.shikkhokplus.app.feature.profile

import androidx.compose.ui.test.assertIsNotEnabled
import com.shikkhokplus.app.core.model.PostalAddress
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.feature.profile.ui.EditProfileScreen
import com.shikkhokplus.app.feature.profile.ui.TAG_EDIT_PROFILE_CLOSE
import com.shikkhokplus.app.core.ui.TAG_ADDRESS_CITY
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_NAME
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_PHONE
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_SAVE
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * Edit profile (S4), rendered.
 *
 * **The screen says a profile edit changes no teacher's roster**
 * [BR3.1, AC1.5.3]. The two names answer different questions and only
 * the server knows which table it reads, so a person has no way to
 * discover this except by being told, here, where the change is made.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class EditProfileScreenTest {

    private companion object {
        val HOME = PostalAddress("House 12", "Road 5", "Dhaka", "1205")
    }


    @get:Rule
    val compose = createComposeRule()

    private fun render(
        state: ProfileUiState = ProfileUiState.Editing(selfName = "Rahim", address = HOME),
        onSave: (String, PostalAddress) -> Unit = { _, _ -> },
        onClose: () -> Unit = {},
        onRetry: () -> Unit = {},
    ) {
        compose.setContent {
            EditProfileScreen(
                state = state,
                phone = "+8801611477203",
                onSave = onSave,
                onClose = onClose,
                onRetry = onRetry,
            )
        }
    }

    @Test
    fun `the form is titled Edit profile and labels the name Full name`() {
        render()

        compose.onNodeWithText("Edit profile").assertIsDisplayed()
        compose.onNodeWithText("Full name").assertIsDisplayed()
    }

    @Test
    fun `editing says the teacher's roster is unaffected`() {
        render()

        compose
            .onNodeWithText("does not change the name", substring = true)
            .assertIsDisplayed()
    }

    @Test
    fun `the sign-in number is shown, read-only and formatted`() {
        render()

        compose.onNodeWithTag(TAG_PROFILE_PHONE).performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("01611-477203").assertIsDisplayed()
        compose.onNodeWithText("cannot be changed", substring = true).assertIsDisplayed()
    }

    @Test
    fun `saving reports both edited values`() {
        var saved: Pair<String, PostalAddress>? = null
        render(onSave = { name, address -> saved = name to address })

        compose.onNodeWithTag(TAG_PROFILE_NAME).performTextClearance()
        compose.onNodeWithTag(TAG_PROFILE_NAME).performTextInput("Karim")
        compose.onNodeWithTag(TAG_ADDRESS_CITY).performScrollTo().performTextClearance()
        compose.onNodeWithTag(TAG_ADDRESS_CITY).performTextInput("Khulna")
        compose.onNodeWithTag(TAG_PROFILE_SAVE).performScrollTo().performClick()

        assertEquals("Karim" to HOME.copy(city = "Khulna"), saved)
    }

    @Test
    fun `save waits for all four address parts, and a bad postcode says so`() {
        // The address is required (decided 2026-11-05).
        render(state = ProfileUiState.Editing(selfName = "Rahim", address = HOME.copy(postcode = "12")))

        compose.onNodeWithTag(TAG_PROFILE_SAVE).performScrollTo().assertIsNotEnabled()
        compose.onNodeWithText("Postcodes have 4 digits").performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `the X closes without saving`() {
        var closes = 0
        var saves = 0
        render(onSave = { _, _ -> saves++ }, onClose = { closes++ })

        compose.onNodeWithTag(TAG_EDIT_PROFILE_CLOSE).performClick()

        assertEquals(1, closes)
        assertEquals(0, saves)
    }

    @Test
    fun `a retryable failed save offers a retry`() {
        var retried = 0
        render(
            state = ProfileUiState.Failed(messageKey = "error.network.unreachable", retryable = true),
            onRetry = { retried++ },
        )

        compose.onNodeWithText("Try again", substring = true).performClick()
        assertEquals(1, retried)
    }
}
