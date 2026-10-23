package com.shikkhokplus.app.feature.guardian

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.GuardianChildDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * The guardian home's mapping decisions.
 *
 * Targeting the mapper rather than "the ViewModel", per `team.md`.
 */
class GuardianStateMapperTest {

    private fun dto(
        id: String,
        name: String,
        batch: String = "Physics",
        teacher: String? = "Karim Sir",
    ): GuardianChildDto =
        GuardianChildDto(
            enrollmentId = id,
            displayName = name,
            batchName = batch,
            teacherDisplayName = teacher,
        )

    @Test
    fun `one child is OneChild, not a list of length one`() {
        // [frontend-components]. A composable writing
        // `if (children.size > 1)` would be deciding whether a switcher
        // is needed. The states are separate so that decision is made
        // once, here, where a test can reach it.
        val state = GuardianStateMapper.afterLoad(listOf(dto("e-1", "Rahim")))

        val one = assertIs<GuardianUiState.OneChild>(state)
        assertEquals("Rahim", one.child.displayName)
    }

    @Test
    fun `several children is a separate state carrying the selection`() {
        val state =
            GuardianStateMapper.afterLoad(
                listOf(dto("e-1", "Rahim"), dto("e-2", "Karima")),
            )

        val several = assertIs<GuardianUiState.SeveralChildren>(state)
        assertEquals(2, several.children.size)
        // A guardian lands somewhere rather than on a chooser they did
        // not ask for, matching the lens's own `child_enrollment_id`.
        assertEquals("e-1", several.selected.enrollmentId)
    }

    @Test
    fun `no children is Empty, not a Loaded with none`() {
        // "Nothing to show yet" needs an explanation and a blank screen
        // gives none. A declined guardian link lands here: the seat
        // stays in that guardian's invitations [BR5.4].
        assertEquals(
            GuardianUiState.Empty,
            GuardianStateMapper.afterLoad(emptyList()),
        )
    }

    @Test
    fun `the batch is carried even in the single-child case`() {
        // [AC2.8.5]. That is where attribution is MOST needed: there is
        // no selection list to have shown it.
        val one =
            assertIs<GuardianUiState.OneChild>(
                GuardianStateMapper.afterLoad(
                    listOf(dto("e-1", "Rahim", batch = "Chemistry")),
                ),
            )

        assertEquals("Chemistry", one.child.batchName)
    }

    @Test
    fun `switching child REPLACES the selection rather than stacking`() {
        // [BR4.2, NFR14.30, AC9.4.2]. The state after a switch carries
        // the SAME children and a different selection: there is no
        // history, no stack and no previous destination. That absence
        // is what makes Back unable to reach the previous child's data.
        val before =
            assertIs<GuardianUiState.SeveralChildren>(
                GuardianStateMapper.afterLoad(
                    listOf(dto("e-1", "Rahim"), dto("e-2", "Karima")),
                ),
            )

        val after =
            assertIs<GuardianUiState.SeveralChildren>(
                GuardianStateMapper.afterChildSelected(before, before.children[1]),
            )

        assertEquals("Karima", after.selected.displayName)
        assertEquals(before.children, after.children)
        // The previous selection is GONE from the new state, not
        // recorded beside it. A field holding "where we came from"
        // would be the back stack this design does not have.
        assertEquals(false, after.selected == before.selected)
    }

    @Test
    fun `selecting a child this guardian does not reach is refused`() {
        // The authorization that matters is the server's — every
        // request names the child as a path parameter and is scoped by
        // the lens [BR4.1] — but selecting an unreachable seat would
        // put a child's name on screen before the server ever refused
        // the data behind it.
        val state =
            assertIs<GuardianUiState.SeveralChildren>(
                GuardianStateMapper.afterLoad(
                    listOf(dto("e-1", "Rahim"), dto("e-2", "Karima")),
                ),
            )

        val result =
            GuardianStateMapper.afterChildSelected(
                state,
                GuardianChild("e-99", "Someone else", "Physics", null),
            )

        assertIs<GuardianUiState.Failed>(result)
    }

    @Test
    fun `retryable is read from the envelope, never inferred`() {
        val failed =
            assertIs<GuardianUiState.Failed>(
                GuardianStateMapper.afterError(
                    ErrorEnvelope(
                        ErrorBody(
                            code = "AUTHZ_LENS_NOT_AVAILABLE",
                            retryable = false,
                            messageKey = "authz.lens.not_available",
                        ),
                    ),
                ),
            )

        assertEquals("authz.lens.not_available", failed.messageKey)
        assertEquals(false, failed.retryable)
    }

    @Test
    fun `a transport failure is retryable`() {
        val failed =
            assertIs<GuardianUiState.Failed>(
                GuardianStateMapper.afterTransportFailure(),
            )

        assertEquals(GuardianStateMapper.OFFLINE_KEY, failed.messageKey)
        assertEquals(true, failed.retryable)
    }
}
