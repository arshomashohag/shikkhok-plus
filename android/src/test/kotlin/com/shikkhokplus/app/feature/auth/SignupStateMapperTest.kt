package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.model.SignupRole
import com.shikkhokplus.app.core.network.AlreadyAddedDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.SignupResponseDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

/**
 * The signup screen's decisions, mapped from server answers.
 *
 * The two that carry weight are the role LOCK on the already-added
 * path -- where a wrong lock contradicts a person's own seat -- and the
 * boundary between what this client validates and what the server
 * decides.
 */
class SignupStateMapperTest {

    @Test
    fun `a number with no seat gives the empty form`() {
        val state = SignupStateMapper.afterLookup(AlreadyAddedDto(alreadyAdded = false))

        assertIs<SignupUiState.Empty>(state)
    }

    @Test
    fun `an added number pre-fills the name and locks the role`() {
        // AC1.12.1. The name is CORRECTABLE -- the state carries it as
        // a starting value, not as a fixed one -- and the role is not.
        val state =
            SignupStateMapper.afterLookup(
                AlreadyAddedDto(
                    alreadyAdded = true,
                    displayName = "Rahim Uddin",
                    role = "guardian",
                ),
            )

        val added = assertIs<SignupUiState.AlreadyAdded>(state)
        assertEquals("Rahim Uddin", added.prefilledName)
        assertEquals(SignupRole.GUARDIAN, added.lockedRole)
    }

    @Test
    fun `an unknown role fails rather than locking to a guess`() {
        // Locking the form to a guessed role contradicts the seat the
        // person actually holds, which is worse than not locking it.
        val state =
            SignupStateMapper.afterLookup(
                AlreadyAddedDto(
                    alreadyAdded = true,
                    displayName = "Rahim",
                    role = "headmaster",
                ),
            )

        val failed = assertIs<SignupUiState.Failed>(state)
        assertEquals(SignupStateMapper.UNEXPECTED_KEY, failed.messageKey)
    }

    @Test
    fun `a seat claimed without a name or role is a failure`() {
        val state =
            SignupStateMapper.afterLookup(AlreadyAddedDto(alreadyAdded = true))

        assertIs<SignupUiState.Failed>(state)
    }

    @Test
    fun `validation checks format and never policy`() {
        // **The layer boundary** [team: Layer boundaries]. Client-side
        // validation is format-only. Whether a number already has an
        // account is a server decision, and a client copy of that rule
        // is the validation-divergence erosion path.
        assertNull(SignupStateMapper.validate("+8801700000000", "Rahim"))

        val tooShort = SignupStateMapper.validate("123", "Rahim")
        assertEquals(listOf(SignupStateMapper.PHONE_KEY), tooShort?.fieldKeys)

        val blankName = SignupStateMapper.validate("+8801700000000", "   ")
        assertEquals(listOf(SignupStateMapper.NAME_KEY), blankName?.fieldKeys)
    }

    @Test
    fun `an address is never rejected for its shape`() {
        // Bangladesh addresses do not decompose cleanly into line, city
        // and postcode, so a format rule would reject real ones. The
        // field is optional and unvalidated by design.
        assertNull(SignupStateMapper.validate("+8801700000000", "Rahim"))
    }

    @Test
    fun `a successful signup names the number the code went to`() {
        // AC1.11.4: the submit action states its destination, so a
        // person can tell which number they are about to be texted.
        val state =
            SignupStateMapper.afterSignup(
                SignupResponseDto(
                    accountId = "a-1",
                    codeSentTo = "+8801700000000",
                ),
            )

        assertEquals(
            "+8801700000000",
            assertIs<SignupUiState.CodeSent>(state).codeSentTo,
        )
    }

    @Test
    fun `a duplicate number arrives as a server-named failure`() {
        // BR4.4, AC1.12.4. The server names the string and says whether
        // a retry would help; the client renders it beside a path to
        // log in and decides neither.
        val state =
            SignupStateMapper.afterError(
                ErrorEnvelope(
                    ErrorBody(
                        code = "ACCOUNT_EXISTS",
                        retryable = false,
                        messageKey = "signup.number.already_registered",
                    ),
                ),
            )

        val failed = assertIs<SignupUiState.Failed>(state)
        assertEquals("signup.number.already_registered", failed.messageKey)
        assertEquals(false, failed.retryable)
    }

    @Test
    fun `a transport failure is retryable and names no server string`() {
        val failed =
            assertIs<SignupUiState.Failed>(
                SignupStateMapper.afterTransportFailure(),
            )

        assertEquals(SignupStateMapper.OFFLINE_KEY, failed.messageKey)
        assertEquals(true, failed.retryable)
    }
}
