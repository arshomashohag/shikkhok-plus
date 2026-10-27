package com.shikkhokplus.app.feature.invitations

import com.shikkhokplus.app.core.network.DecisionDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.InvitationDto
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * The invitations ViewModel's own state machine.
 *
 * [InvitationsStateMapperTest] covers the mapping; this covers what
 * only the ViewModel has — the in-flight states, the explicit retry,
 * and **which decline sheet a holder is shown**, which is the rule a
 * single confirmation written once got wrong [BR5.2].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class InvitationsViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun seat(role: String) =
        InvitationDto(
            enrollmentId = "e-1",
            batchName = "Physics",
            subject = listOf("Physics"),
            decision = "pending",
            role = role,
        )

    private class FakeRepository(
        var listResult: AuthResult<List<InvitationDto>> = AuthResult.Ok(emptyList()),
        var decisionResult: AuthResult<DecisionDto> =
            AuthResult.Ok(DecisionDto("e-1", "accepted")),
    ) : InvitationsRepository {
        var listCalls = 0
        var acceptCalls = 0
        var declineCalls = 0

        override suspend fun list(): AuthResult<List<InvitationDto>> {
            listCalls++
            return listResult
        }

        override suspend fun detail(enrollmentId: String): AuthResult<InvitationDto> =
            when (val r = listResult) {
                is AuthResult.Ok -> AuthResult.Ok(r.value.first())
                is AuthResult.Refused -> r
                AuthResult.TransportFailure -> AuthResult.TransportFailure
            }

        override suspend fun accept(enrollmentId: String): AuthResult<DecisionDto> {
            acceptCalls++
            return decisionResult
        }

        override suspend fun decline(enrollmentId: String): AuthResult<DecisionDto> {
            declineCalls++
            return decisionResult
        }
    }

    @Test
    fun `a student declining reads the student sheet`() = runTest(dispatcher) {
        // A student's decline stops the fee being owed, and the sheet
        // says so.
        val repo = FakeRepository(listResult = AuthResult.Ok(listOf(seat("student"))))
        val model = InvitationsViewModel(repo)

        model.load()
        advanceUntilIdle()
        model.confirmDecline("e-1")

        val state = assertIs<InvitationsUiState.ConfirmingDecline>(model.state.value)
        assertEquals(DeclineSheet.STUDENT, state.sheet)
    }

    @Test
    fun `a guardian declining reads the guardian sheet`() = runTest(dispatcher) {
        // **The defect this exists to prevent.** A guardian's decline
        // withdraws only their own lens; the student's obligation is
        // entirely intact. One confirmation shown to both roles told a
        // guardian a debt was cancelled when it was not.
        val repo = FakeRepository(listResult = AuthResult.Ok(listOf(seat("guardian"))))
        val model = InvitationsViewModel(repo)

        model.load()
        advanceUntilIdle()
        model.confirmDecline("e-1")

        val state = assertIs<InvitationsUiState.ConfirmingDecline>(model.state.value)
        assertEquals(DeclineSheet.GUARDIAN, state.sheet)
    }

    @Test
    fun `an unknown role falls to the student sheet, not the guardian one`() =
        runTest(dispatcher) {
            // The safer default. The guardian sheet is the one that
            // would wrongly promise a fee had stopped, so an
            // unrecognised value must not reach it.
            val repo = FakeRepository(listResult = AuthResult.Ok(listOf(seat("owl"))))
            val model = InvitationsViewModel(repo)

            model.load()
            advanceUntilIdle()
            model.confirmDecline("e-1")

            val state = assertIs<InvitationsUiState.ConfirmingDecline>(model.state.value)
            assertEquals(DeclineSheet.STUDENT, state.sheet)
        }

    @Test
    fun `asking for a confirmation makes no network call`() = runTest(dispatcher) {
        // Opening a sheet is not a decision. A call here would decline
        // the seat before the person had read what declining does.
        val repo = FakeRepository(listResult = AuthResult.Ok(listOf(seat("student"))))
        val model = InvitationsViewModel(repo)

        model.load()
        advanceUntilIdle()
        model.confirmDecline("e-1")
        advanceUntilIdle()

        assertEquals(0, repo.declineCalls, "a confirmation must not decide")
    }

    @Test
    fun `dismissing the sheet returns to the seat, undecided`() =
        runTest(dispatcher) {
            val repo =
                FakeRepository(listResult = AuthResult.Ok(listOf(seat("student"))))
            val model = InvitationsViewModel(repo)

            model.load()
            advanceUntilIdle()
            model.confirmDecline("e-1")
            model.dismissSheet()
            advanceUntilIdle()

            assertIs<InvitationsUiState.Detail>(model.state.value)
            assertEquals(0, repo.declineCalls)
        }

    @Test
    fun `accepting calls the accept route, never decline`() = runTest(dispatcher) {
        val repo = FakeRepository()
        val model = InvitationsViewModel(repo)

        model.accept("e-1")
        advanceUntilIdle()

        assertEquals(1, repo.acceptCalls)
        assertEquals(0, repo.declineCalls, "accepting must never decline")
    }

    @Test
    fun `a transport failure is retryable and retry repeats the action`() =
        runTest(dispatcher) {
            val repo = FakeRepository(listResult = AuthResult.TransportFailure)
            val model = InvitationsViewModel(repo)

            model.load()
            advanceUntilIdle()

            val state = assertIs<InvitationsUiState.Failed>(model.state.value)
            assertEquals(true, state.retryable)
            assertEquals(1, repo.listCalls)

            model.retry()
            advanceUntilIdle()
            assertEquals(2, repo.listCalls)
        }

    @Test
    fun `a refusal carries the server's own message`() = runTest(dispatcher) {
        val repo =
            FakeRepository(
                listResult =
                    AuthResult.Refused(
                        ErrorEnvelope(
                            ErrorBody(
                                code = "FORBIDDEN",
                                messageKey = "error.forbidden",
                                retryable = false,
                            ),
                        ),
                    ),
            )
        val model = InvitationsViewModel(repo)

        model.load()
        advanceUntilIdle()

        val state = assertIs<InvitationsUiState.Failed>(model.state.value)
        assertEquals("error.forbidden", state.messageKey)
    }
}
