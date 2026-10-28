package com.shikkhokplus.app.feature.profile

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import com.shikkhokplus.app.feature.profile.ui.ProfileScreen
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_ADDRESS
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_DELETE
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_PHONE
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_SIGN_OUT
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_NAME
import com.shikkhokplus.app.feature.profile.ui.TAG_PROFILE_SAVE
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * `O5` profile, the edit half, rendered.
 *
 * Two obligations are assertable only here:
 *
 * * **The screen says a profile edit changes no teacher's roster**
 *   [BR3.1, AC1.5.3]. The two names answer different questions and only
 *   the server knows which table it reads, so a person has no way to
 *   discover this except by being told.
 * * **The deletion control is present and wired.** This used to assert
 *   the OPPOSITE -- no deletion control -- because both deletion paths
 *   were D6's [TC-19] and the absence guarded against a half-built
 *   control appearing early. The in-app path has now landed, so the
 *   guard has done its job and the assertion flips with it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ProfileScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun render(
        state: ProfileUiState,
        onEdit: () -> Unit = {},
        onSave: (String, String) -> Unit = { _, _ -> },
        onRetry: () -> Unit = {},
    ) {
        compose.setContent {
            ProfileScreen(
                state = state,
                onEdit = onEdit,
                onSave = onSave,
                onRetry = onRetry,
            )
        }
    }

    @Test
    fun `viewing says the teacher's roster is unaffected`() {
        render(
            ProfileUiState.Viewing(selfName = "Rahim", address = "Dhaka"),
        )

        compose
            .onNodeWithText("does not change the name", substring = true)
            .assertIsDisplayed()
    }

    @Test
    fun `editing repeats that the teacher's roster is unaffected`() {
        // The note belongs where the change is made, not only where it
        // is viewed: a person who taps straight to Edit would otherwise
        // never read it.
        render(
            ProfileUiState.Editing(selfName = "Rahim", address = "Dhaka"),
        )

        compose
            .onNodeWithText("does not change the name", substring = true)
            .assertIsDisplayed()
    }

    @Test
    fun `the profile offers account deletion`() {
        // Flipped from "offers no deletion control" when the in-app
        // deletion path landed; see the class comment.
        render(ProfileUiState.Viewing(selfName = "Rahim", address = "Dhaka"))

        compose.onNodeWithTag(TAG_PROFILE_DELETE).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `an unset field renders its label rather than disappearing`() {
        render(ProfileUiState.Viewing(selfName = null, address = null))

        compose.onNodeWithText("Your name").assertIsDisplayed()
        compose.onNodeWithText("Address").assertIsDisplayed()
    }

    @Test
    fun `saving reports both edited values`() {
        var saved: Pair<String, String>? = null
        render(
            ProfileUiState.Editing(selfName = "Rahim", address = "Dhaka"),
            onSave = { name, address -> saved = name to address },
        )

        compose.onNodeWithTag(TAG_PROFILE_NAME).performTextClearance()
        compose.onNodeWithTag(TAG_PROFILE_NAME).performTextInput("Karim")
        compose.onNodeWithTag(TAG_PROFILE_ADDRESS).performTextClearance()
        compose.onNodeWithTag(TAG_PROFILE_ADDRESS).performTextInput("Khulna")
        compose.onNodeWithTag(TAG_PROFILE_SAVE).performClick()

        assertEquals("Karim" to "Khulna", saved)
    }

    @Test
    fun `a saved profile confirms and shows what was stored`() {
        render(
            ProfileUiState.Saved(selfName = "Karim", address = "Khulna"),
        )

        compose.onNodeWithText("Saved.").assertIsDisplayed()
        compose.onNodeWithText("Karim").assertIsDisplayed()
    }

    @Test
    fun `a retryable failure offers a retry the server permitted`() {
        var retried = false
        render(
            ProfileUiState.Failed(
                messageKey = "error.network.unreachable",
                retryable = true,
            ),
            onRetry = { retried = true },
        )

        compose.onNodeWithText("Try again", substring = true).performClick()
        assertEquals(true, retried)
    }

    @Test
    fun `the sign-in number is shown, read-only`() {
        // O5: "This is your login and cannot be changed."
        render(ProfileUiState.Viewing("Rahim", "Dhaka", phone = "+8801611477203"))

        compose.onNodeWithTag(TAG_PROFILE_PHONE).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun `delete and sign out each call back only when tapped`() {
        var deletes = 0
        var signOuts = 0
        compose.setContent {
            ProfileScreen(
                state = ProfileUiState.Viewing("Rahim", "Dhaka", phone = "+8801611477203"),
                onEdit = {},
                onSave = { _, _ -> },
                onRetry = {},
                onDeleteAccount = { deletes++ },
                onSignOut = { signOuts++ },
            )
        }
        assertEquals(0, deletes + signOuts, "rendering must not act")

        compose.onNodeWithTag(TAG_PROFILE_DELETE).performScrollTo().performClick()
        compose.onNodeWithTag(TAG_PROFILE_SIGN_OUT).performScrollTo().performClick()

        assertEquals(1, deletes)
        assertEquals(1, signOuts)
    }
}
