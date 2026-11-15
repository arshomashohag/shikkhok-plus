package com.shikkhokplus.app.core.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The username field's one client rule: the TRIMMED text fits the
 * schema's 64 characters [NFR3.9, FR11.3]. FR1's 20 is the server's, so
 * 21 is accepted here and refused there.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class UsernameFieldTest {

    @get:Rule
    val compose = createComposeRule()

    private var value by mutableStateOf("")

    private fun render() {
        compose.setContent {
            ShikkhokTheme {
                UsernameField(
                    value = value,
                    onValueChange = { value = it },
                    label = "Username",
                    autofill = AutofillHint.NEW_USERNAME,
                    fieldModifier = Modifier.testTag(FIELD),
                )
            }
        }
    }

    @Test
    fun `an edit that would make 65 characters is rejected and the field keeps 64`() {
        render()
        compose.onNodeWithTag(FIELD).performTextReplacement("a".repeat(64))

        compose.onNodeWithTag(FIELD).performTextInput("b")

        assertEquals("a".repeat(64), value)
    }

    @Test
    fun `64 characters are accepted`() {
        render()

        compose.onNodeWithTag(FIELD).performTextReplacement("a".repeat(64))

        assertEquals(64, value.length)
    }

    @Test
    fun `64 characters with spaces round them are accepted, because the cap is on the trimmed text`() {
        render()
        val padded = "  " + "a".repeat(64) + "  "

        compose.onNodeWithTag(FIELD).performTextReplacement(padded)

        assertEquals(padded, value)
    }

    @Test
    fun `21 characters are accepted, FR1's limit being the server's`() {
        render()

        compose.onNodeWithTag(FIELD).performTextReplacement("a".repeat(21))

        assertEquals(21, value.length)
    }

    @Test
    fun `the rule itself, without a screen`() {
        assertEquals(true, usernameEditAccepted("a".repeat(64)))
        assertEquals(false, usernameEditAccepted("a".repeat(65)))
        assertEquals(true, usernameEditAccepted(" " + "a".repeat(64) + " "))
    }

    private companion object {
        const val FIELD = "username_field_under_test"
    }
}
