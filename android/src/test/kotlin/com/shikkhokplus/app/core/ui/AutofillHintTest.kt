package com.shikkhokplus.app.core.ui

import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.autofill.AutofillType
import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * Each hint asks the platform for the right kind of value [TSD-4]: an
 * existing username where one is filled, a new one where one is created,
 * and the three existing hints unchanged.
 */
@OptIn(ExperimentalComposeUiApi::class)
class AutofillHintTest {

    @Test
    fun `a username to fill is Username`() {
        assertEquals(AutofillType.Username, autofillTypeOf(AutofillHint.USERNAME))
    }

    @Test
    fun `a username being created is NewUsername`() {
        assertEquals(AutofillType.NewUsername, autofillTypeOf(AutofillHint.NEW_USERNAME))
    }

    @Test
    fun `the existing three are unchanged`() {
        assertEquals(AutofillType.EmailAddress, autofillTypeOf(AutofillHint.EMAIL))
        assertEquals(AutofillType.Password, autofillTypeOf(AutofillHint.PASSWORD))
        assertEquals(AutofillType.NewPassword, autofillTypeOf(AutofillHint.NEW_PASSWORD))
    }
}
