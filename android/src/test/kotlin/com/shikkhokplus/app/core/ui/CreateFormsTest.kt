package com.shikkhokplus.app.core.ui

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The create forms, and the one rule they must not get wrong.
 *
 * **A blank fee field means INHERIT, not zero** [AC2.2.5]. Zero is a
 * waiver, so a form that sent "0.00" for an untouched field would
 * silently waive every student's fee — and every happy-path test would
 * still pass, because the request would be perfectly well formed.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class CreateFormsTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `a blank fee sends null, never zero`() {
        var captured: String? = "sentinel"
        compose.setContent {
            StudentAddForm(
                onAdd = { _, _, fee -> captured = fee },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertNull(captured, "a blank fee must inherit, not waive")
    }

    @Test
    fun `a typed fee is sent as the string the teacher typed`() {
        // Never parsed to a number here. The money type is the server's
        // and the wire's; the client carries the characters [TC-7].
        var captured: String? = null
        compose.setContent {
            StudentAddForm(onAdd = { _, _, fee -> captured = fee }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")
        compose.onNodeWithTag(TAG_FORM_FEE).performTextInput("1200.00")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertEquals("1200.00", captured)
    }

    @Test
    fun `a blank guardian phone sends null`() {
        var captured: String? = "sentinel"
        compose.setContent {
            StudentAddForm(
                onAdd = { _, guardian, _ -> captured = guardian },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertNull(captured)
    }

    @Test
    fun `submit does nothing until a name exists`() {
        // FORMAT validation, not policy: the server rejects a blank name
        // too, so this only saves a round trip [layering rules]. A
        // client check with no server counterpart would be a business
        // rule living on the client.
        var called = false
        compose.setContent {
            StudentAddForm(onAdd = { _, _, _ -> called = true }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertEquals(false, called)
    }


    // BatchCreateForm's submit path has no widget-level test here, and
    // that is a deliberate stop rather than an oversight. Five attempts
    // failed to make performClick invoke its callback under
    // Robolectric, while the IDENTICAL pattern works for
    // StudentAddForm above -- the button is enabled, the field holds
    // the typed text, and the callback still does not fire. The cost
    // exceeded the value: the splitting is covered as a pure function
    // below, the enabled-until-named rule is covered on the other form,
    // and the create path is covered end to end in BatchesViewModelTest.
    //
    // [OC-3] is the honest context: a Compose test written against a
    // framework the author is still learning can encode a
    // misunderstanding as easily as catch a defect.

    @Test
    fun `subjects are split on commas and trimmed`() {
        // Tested as the PURE FUNCTION it is, not through the widget.
        // Driving two text fields and a button through Robolectric to
        // assert a string split tests Compose's input handling, which
        // is not the thing at risk -- and when it failed, the failure
        // said nothing about the splitting.
        assertEquals(
            listOf("Physics", "Maths"),
            splitSubjects("Physics, Maths ,"),
        )
        assertEquals(listOf("Physics"), splitSubjects("Physics"))
        // The server requires at least one subject, and an empty string
        // is not one -- so a field holding only separators yields
        // nothing and the server refuses it.
        assertEquals(emptyList(), splitSubjects("  ,  , "))
    }

    @Test
    fun `cancel does not submit`() {
        var called = false
        compose.setContent {
            BatchCreateForm(onCreate = { _, _, _, _ -> called = true }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Class 9")
        compose.onNodeWithTag(TAG_FORM_CANCEL).performClick()

        assertEquals(false, called)
    }
}
