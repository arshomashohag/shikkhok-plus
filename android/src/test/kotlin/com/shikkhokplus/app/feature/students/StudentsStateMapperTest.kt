package com.shikkhokplus.app.feature.students

import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Which contact a student screen shows, and where a refusal goes [W7].
 *
 * Both are decisions, so they are the mapper's and are tested here
 * rather than left to a composable [team: Layer boundaries].
 */
class StudentsStateMapperTest {

    @Test
    fun `a phone alone is the contact line`() {
        assertEquals("+8801812345678", StudentsStateMapper.contactLine("+8801812345678", null))
    }

    @Test
    fun `an email alone is the contact line when no phone is recorded`() {
        assertEquals("rafiq@example.com", StudentsStateMapper.contactLine(null, "rafiq@example.com"))
    }

    @Test
    fun `both are shown when both are recorded, phone first`() {
        assertEquals(
            "+8801812345678 · rafiq@example.com",
            StudentsStateMapper.contactLine("+8801812345678", "rafiq@example.com"),
        )
    }

    @Test
    fun `neither, or blanks, is no line at all`() {
        assertNull(StudentsStateMapper.contactLine(null, null))
        assertNull(StudentsStateMapper.contactLine(" ", ""))
    }

    @Test
    fun `a taken student email goes under the student email field, nothing else does`() {
        assertTrue(StudentsStateMapper.isStudentEmailRefusal(WriteState.Failed("student.email.taken", false)))
        assertFalse(StudentsStateMapper.isStudentEmailRefusal(WriteState.Failed("email.invalid", false)))
        assertFalse(StudentsStateMapper.isStudentEmailRefusal(WriteState.Saved))
    }

    @Test
    fun `the server's refusal reaches the form unchanged`() {
        assertEquals(
            WriteState.Failed("student.email.taken", retryable = false),
            StudentsStateMapper.written(
                AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, "student.email.taken"))),
            ),
        )
    }
}
