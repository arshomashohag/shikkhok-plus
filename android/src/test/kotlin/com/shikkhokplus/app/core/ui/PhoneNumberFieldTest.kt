package com.shikkhokplus.app.core.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performImeAction
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * The number is judged when the person leaves the field, never per key.
 *
 * Reported from a device: the sign-up form judged the number on every
 * key press, so the first digit was already "wrong". These tests type
 * a number, assert nothing was said while typing, then move focus to a
 * neighbouring field and assert what is said under the number.
 *
 * Focus is moved with a focus request rather than a click: under
 * Robolectric a click on another text field does not take focus, while
 * on a device a tap does.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PhoneNumberFieldTest {

    @get:Rule
    val compose = createComposeRule()

    private val message = "Enter an 11-digit mobile number, like 01711-234567"

    private fun render(onLeft: (String) -> Unit = {}) {
        compose.setContent {
            var phone by remember { mutableStateOf("") }
            var other by remember { mutableStateOf("") }
            Column {
                PhoneNumberField(
                    value = phone,
                    onValueChange = { phone = it },
                    label = "Mobile number",
                    onLeftWithValidNumber = onLeft,
                    fieldModifier = Modifier.testTag(PHONE),
                )
                OutlinedTextField(
                    value = other,
                    onValueChange = { other = it },
                    label = { Text("Name") },
                    modifier = Modifier.testTag(NEXT),
                )
            }
        }
    }

    @Test
    fun `nothing is said while the number is being typed`() {
        render()
        compose.onNodeWithTag(PHONE).performClick()
        compose.onNodeWithTag(PHONE).performTextInput("017")

        compose.onNodeWithText(message).assertDoesNotExist()
    }

    @Test
    fun `leaving the field with a wrong number says so under it`() {
        render()
        compose.onNodeWithTag(PHONE).performClick()
        compose.onNodeWithTag(PHONE).performTextInput("017")
        compose.onNodeWithTag(NEXT).performSemanticsAction(SemanticsActions.RequestFocus)

        compose.onNodeWithText(message).assertExists()
    }

    @Test
    fun `editing again clears the message without judging`() {
        render()
        compose.onNodeWithTag(PHONE).performClick()
        compose.onNodeWithTag(PHONE).performTextInput("017")
        compose.onNodeWithTag(NEXT).performSemanticsAction(SemanticsActions.RequestFocus)
        compose.onNodeWithTag(PHONE).performClick()
        compose.onNodeWithTag(PHONE).performTextInput("1")

        compose.onNodeWithText(message).assertDoesNotExist()
    }

    @Test
    fun `leaving with a valid number reports it and says nothing`() {
        val left = mutableListOf<String>()
        render(onLeft = { left.add(it) })
        compose.onNodeWithTag(PHONE).performClick()
        compose.onNodeWithTag(PHONE).performTextInput("01711-234567")
        compose.onNodeWithTag(NEXT).performSemanticsAction(SemanticsActions.RequestFocus)

        compose.onNodeWithText(message).assertDoesNotExist()
        assertEquals(listOf("01711-234567"), left)
    }

    @Test
    fun `the keyboard's done key leaves the field and checks it`() {
        render()
        compose.onNodeWithTag(PHONE).performClick()
        compose.onNodeWithTag(PHONE).performTextInput("017")
        compose.onNodeWithTag(PHONE).performImeAction()

        compose.onNodeWithText(message).assertExists()
    }

    @Test
    fun `an untouched field is never judged`() {
        render()
        compose.onNodeWithTag(NEXT).performSemanticsAction(SemanticsActions.RequestFocus)

        compose.onNodeWithText(message).assertDoesNotExist()
    }

    private companion object {
        const val PHONE = "phone"
        const val NEXT = "next"
    }
}
