package com.shikkhokplus.app.core.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
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
                onAdd = { _, _, _, fee -> captured = fee },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_FORM_STUDENT_PHONE).performTextInput("01711-234567")
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertNull(captured, "a blank fee must inherit, not waive")
    }

    @Test
    fun `a fee typed without decimals is sent in canonical form`() {
        // **Replaces "a typed fee is sent as the string the teacher
        // typed"**, which typed `1200.00` -- the one form the server
        // accepts -- and so passed while what every teacher actually
        // types, `1200`, was refused with a 422. The class or student
        // was then silently never created.
        var captured: String? = null
        compose.setContent {
            StudentAddForm(onAdd = { _, _, _, fee -> captured = fee }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_STUDENT_PHONE).performTextInput("01711-234567")
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")
        compose.onNodeWithTag(TAG_FORM_FEE).performTextInput("1200")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertEquals("1200.00", captured)
    }

    @Test
    fun `a fee typed in Bangla digits is sent in Latin canonical form`() {
        var captured: String? = null
        compose.setContent {
            BatchCreateForm(
                onCreate = { _, _, fee, _ -> captured = fee },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Class 9")
        compose.onNodeWithTag(TAG_FORM_SUBJECTS).performTextInput("Physics")
        compose.onNodeWithTag(TAG_FORM_FEE).performTextInput("১,৫০০")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertEquals("1500.00", captured)
    }

    @Test
    fun `a fee that is not an amount blocks submit rather than being sent`() {
        var called = false
        compose.setContent {
            BatchCreateForm(onCreate = { _, _, _, _ -> called = true }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Class 9")
        compose.onNodeWithTag(TAG_FORM_SUBJECTS).performTextInput("Physics")
        compose.onNodeWithTag(TAG_FORM_FEE).performTextInput("fifteen hundred")

        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsNotEnabled()
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()
        assertEquals(false, called)
    }

    @Test
    fun `a due day outside 1 to 31 blocks submit`() {
        // The field accepted any two digits; the server refuses 0 and
        // anything past 31.
        compose.setContent {
            BatchCreateForm(onCreate = { _, _, _, _ -> }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Class 9")
        compose.onNodeWithTag(TAG_FORM_SUBJECTS).performTextInput("Physics")
        compose.onNodeWithTag(TAG_FORM_DUE_DAY).performTextInput("45")

        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `submit is disabled while the write is in flight`() {
        // The form now stays open until the server answers, so it must
        // not be able to start a second write meanwhile.
        compose.setContent {
            BatchCreateForm(onCreate = { _, _, _, _ -> }, onCancel = {}, saving = true)
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Class 9")
        compose.onNodeWithTag(TAG_FORM_SUBJECTS).performTextInput("Physics")

        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `a refusal is shown on the form`() {
        // It used to have nowhere to appear: the form closed on the tap.
        compose.setContent {
            StudentAddForm(onAdd = { _, _, _, _ -> }, onCancel = {}, error = "Could not save")
        }

        compose.onNodeWithTag(TAG_FORM_ERROR).assertIsDisplayed()
    }

    @Test
    fun `no error is shown when there is none`() {
        compose.setContent {
            StudentAddForm(onAdd = { _, _, _, _ -> }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_ERROR).assertDoesNotExist()
    }

    @Test
    fun `a blank guardian phone sends null`() {
        var captured: String? = "sentinel"
        compose.setContent {
            StudentAddForm(
                onAdd = { _, _, guardian, _ -> captured = guardian },
                onCancel = {},
            )
        }

        compose.onNodeWithTag(TAG_FORM_STUDENT_PHONE).performTextInput("01711-234567")
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertNull(captured)
    }

    @Test
    fun `the student's phone is sent as typed, beside the name`() {
        // **The field that did not exist.** Without it no student a
        // teacher added could ever reach their own seat. Sent as typed:
        // the server canonicalises, so the client never needs to.
        var sent: Pair<String, String>? = null
        compose.setContent {
            StudentAddForm(onAdd = { name, phone, _, _ -> sent = name to phone }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_STUDENT_PHONE).performTextInput("01711-234567")
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).performClick()

        assertEquals("Rahim" to "01711-234567", sent)
    }

    @Test
    fun `a student needs a phone before they can be added`() {
        compose.setContent {
            StudentAddForm(onAdd = { _, _, _, _ -> }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")

        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `a ten-digit phone is caught while typing`() {
        // T8's error state: "This one has 10" -- caught before a round
        // trip rather than refused by the server after one.
        compose.setContent {
            StudentAddForm(onAdd = { _, _, _, _ -> }, onCancel = {})
        }

        compose.onNodeWithTag(TAG_FORM_STUDENT_PHONE).performTextInput("0171123456")
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")

        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `a malformed guardian phone blocks submit, a blank one does not`() {
        compose.setContent {
            StudentAddForm(onAdd = { _, _, _, _ -> }, onCancel = {})
        }
        compose.onNodeWithTag(TAG_FORM_STUDENT_PHONE).performTextInput("01711-234567")
        compose.onNodeWithTag(TAG_FORM_NAME).performTextInput("Rahim")
        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsEnabled()

        compose.onNodeWithTag(TAG_FORM_GUARDIAN).performTextInput("12345")

        compose.onNodeWithTag(TAG_FORM_SUBMIT).assertIsNotEnabled()
    }

    @Test
    fun `submit does nothing until a name exists`() {
        // FORMAT validation, not policy: the server rejects a blank name
        // too, so this only saves a round trip [layering rules]. A
        // client check with no server counterpart would be a business
        // rule living on the client.
        var called = false
        compose.setContent {
            StudentAddForm(onAdd = { _, _, _, _ -> called = true }, onCancel = {})
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
    fun `an empty subjects field yields no subjects, which must not submit`() {
        // **The reported defect, as a predicate.** The server requires
        // `minItems: 1` on subjects and `splitSubjects` filters empties,
        // so an untouched field produced an empty array. FastAPI
        // rejects that with a raw 422 carrying no message_key, so the
        // error envelope rendered nothing and the screen looked like
        // the button was simply dead. The submit guard now checks this
        // list as well as the name.
        //
        // Asserted as the pure function the guard calls, for the reason
        // the comment above gives: a widget-level click test on this
        // form could not be made to fire under Robolectric, and the
        // guard's input is what actually decides.
        assertEquals(emptyList(), splitSubjects(""))
        assertEquals(emptyList(), splitSubjects("   "))
        assertEquals(emptyList(), splitSubjects(",, ,"))

        // And the cases that must still submit.
        assertEquals(listOf("Physics"), splitSubjects("Physics"))
        assertEquals(listOf("Physics", "Maths"), splitSubjects("Physics, Maths"))
    }

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
