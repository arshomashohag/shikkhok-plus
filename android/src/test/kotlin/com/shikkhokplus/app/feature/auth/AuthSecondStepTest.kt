package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.core.network.VerifyResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
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
 * The sign-in's second step [0028], through the ViewModel and the mapper:
 * reaching it, each kind of code, every refusal, and the explicit retry.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class AuthSecondStepTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private val challenged = VerifyResponse(mfaRequired = true, mfaChallenge = "chal", mfaExpiresIn = 300)

    private fun refused(key: String, retryable: Boolean = false) =
        AuthResult.Refused(ErrorEnvelope(ErrorBody(code = "X", retryable = retryable, messageKey = key)))

    /** A server whose answers each test sets, recording each second step. */
    private class FakeRepository(
        var verifyResult: AuthResult<VerifyResponse>,
        var secondResult: AuthResult<TokenResponse> = AuthResult.Ok(TokenResponse("a.b.c", "r1", 900)),
    ) : AuthRepository {
        val sent = mutableListOf<Triple<String, String?, String?>>()

        override suspend fun issue(phone: String): AuthResult<IssueResponse> = AuthResult.Ok(IssueResponse("requested"))

        override suspend fun verify(phone: String, code: String): AuthResult<VerifyResponse> = verifyResult

        override suspend fun verifySecondStep(
            challenge: String,
            code: String?,
            recoveryCode: String?,
        ): AuthResult<TokenResponse> {
            sent += Triple(challenge, code, recoveryCode)
            return secondResult
        }
    }

    /** A ViewModel already at the second step. */
    private fun TestScope.atSecondStep(repository: FakeRepository): AuthViewModel {
        val model = AuthViewModel(repository)
        model.adoptPendingCode("+8801711111111")
        model.submitCode("123456")
        advanceUntilIdle()
        return model
    }

    @Test
    fun `a right SMS code for an account with two-step verification asks for the app code`() = runTest(dispatcher) {
        val model = atSecondStep(FakeRepository(AuthResult.Ok(challenged)))

        assertEquals(AuthUiState.SecondStep(), model.state.value)
    }

    @Test
    fun `an account without it is signed in by the SMS code, untouched`() = runTest(dispatcher) {
        val model = atSecondStep(FakeRepository(AuthResult.Ok(VerifyResponse("a.b.c", "r1", 900))))

        assertEquals(AuthUiState.SignedIn, model.state.value)
    }

    @Test
    fun `the app code checks first, then signs in with the challenge it was given`() = runTest(dispatcher) {
        val repository = FakeRepository(AuthResult.Ok(challenged))
        val model = atSecondStep(repository)

        model.submitSecondStep("654321")
        assertEquals(AuthUiState.SecondStep(checking = true), model.state.value)

        advanceUntilIdle()
        assertEquals(AuthUiState.SignedIn, model.state.value)
        assertEquals(listOf(Triple<String, String?, String?>("chal", "654321", null)), repository.sent)
    }

    @Test
    fun `a recovery code is sent as one, after switching to it`() = runTest(dispatcher) {
        val repository = FakeRepository(AuthResult.Ok(challenged))
        val model = atSecondStep(repository)

        model.toggleRecoveryCode()
        assertEquals(AuthUiState.SecondStep(useRecovery = true), model.state.value)
        model.submitSecondStep("ABCDE-FGHJK")
        advanceUntilIdle()

        assertEquals(listOf(Triple<String, String?, String?>("chal", null, "ABCDE-FGHJK")), repository.sent)
        assertEquals(AuthUiState.SignedIn, model.state.value)
    }

    @Test
    fun `switching back and forth clears a refusal shown for the other kind`() = runTest(dispatcher) {
        val repository = FakeRepository(AuthResult.Ok(challenged), secondResult = refused("mfa.code_wrong"))
        val model = atSecondStep(repository)
        model.submitSecondStep("000000")
        advanceUntilIdle()

        model.toggleRecoveryCode()
        model.toggleRecoveryCode()

        assertEquals(AuthUiState.SecondStep(), model.state.value)
    }

    @Test
    fun `a wrong code stays on the step with the server's words, and the challenge is kept`() =
        runTest(dispatcher) {
            val repository = FakeRepository(AuthResult.Ok(challenged), secondResult = refused("mfa.code_wrong"))
            val model = atSecondStep(repository)

            model.submitSecondStep("000000")
            advanceUntilIdle()
            assertEquals(AuthUiState.SecondStep(messageKey = "mfa.code_wrong", retryable = false), model.state.value)

            repository.secondResult = AuthResult.Ok(TokenResponse("a.b.c", "r1", 900))
            model.submitSecondStep("654321")
            advanceUntilIdle()

            assertEquals(AuthUiState.SignedIn, model.state.value)
            assertEquals(listOf("chal", "chal"), repository.sent.map { it.first })
        }

    @Test
    fun `the lock after five wrong codes is said on the step`() = runTest(dispatcher) {
        val repository = FakeRepository(AuthResult.Ok(challenged), secondResult = refused("mfa.locked"))
        val model = atSecondStep(repository)

        model.submitSecondStep("000000")
        advanceUntilIdle()

        val state = assertIs<AuthUiState.SecondStep>(model.state.value)
        assertEquals("mfa.locked", state.messageKey)
    }

    @Test
    fun `a lapsed challenge goes back to the number with the message`() = runTest(dispatcher) {
        // Retryable or not on the wire, the way on is a new SMS code: the
        // challenge is spent, so the number step owns the next move.
        val repository =
            FakeRepository(AuthResult.Ok(challenged), secondResult = refused("mfa.challenge_expired", retryable = true))
        val model = atSecondStep(repository)

        model.submitSecondStep("654321")
        advanceUntilIdle()
        assertEquals(AuthUiState.Failed("mfa.challenge_expired", retryable = false), model.state.value)

        // The spent challenge is gone: nothing further is sent.
        model.submitSecondStep("654321")
        model.retry()
        advanceUntilIdle()
        assertEquals(1, repository.sent.size)
    }

    @Test
    fun `no answer stays on the step with an explicit retry, and nothing retries by itself`() =
        runTest(dispatcher) {
            val repository = FakeRepository(AuthResult.Ok(challenged), secondResult = AuthResult.TransportFailure)
            val model = atSecondStep(repository)

            model.submitSecondStep("654321")
            advanceUntilIdle()
            assertEquals(
                AuthUiState.SecondStep(messageKey = AuthStateMapper.OFFLINE_KEY, retryable = true),
                model.state.value,
            )
            assertEquals(1, repository.sent.size, "the failure must not auto-retry")

            // THE RETRY: the person taps it, the screen sends the same code.
            repository.secondResult = AuthResult.Ok(TokenResponse("a.b.c", "r1", 900))
            model.submitSecondStep("654321")
            advanceUntilIdle()

            assertEquals(AuthUiState.SignedIn, model.state.value)
            assertEquals(2, repository.sent.size)
        }

    @Test
    fun `back from the step returns to the number and forgets the challenge`() = runTest(dispatcher) {
        val repository = FakeRepository(AuthResult.Ok(challenged))
        val model = atSecondStep(repository)

        model.changeNumber()
        model.submitSecondStep("654321")
        model.toggleRecoveryCode()
        advanceUntilIdle()

        assertEquals(AuthUiState.Idle, model.state.value)
        assertEquals(emptyList(), repository.sent)
    }

    @Test
    fun `nothing switches while a code is being checked`() = runTest(dispatcher) {
        val model = atSecondStep(FakeRepository(AuthResult.Ok(challenged)))

        model.submitSecondStep("654321")
        model.toggleRecoveryCode()

        assertEquals(AuthUiState.SecondStep(checking = true), model.state.value)
        advanceUntilIdle()
    }

    @Test
    fun `a second step with no challenge to carry it is a failure, not a dead end`() {
        assertEquals(
            AuthUiState.Failed(AuthStateMapper.UNEXPECTED_KEY, retryable = false),
            AuthStateMapper.afterVerify(VerifyResponse(mfaRequired = true)),
        )
    }

    @Test
    fun `a pair with a half missing is a failure`() {
        assertEquals(
            AuthUiState.Failed(AuthStateMapper.UNEXPECTED_KEY, retryable = false),
            AuthStateMapper.afterVerify(VerifyResponse(accessToken = "a.b.c")),
        )
    }

    @Test
    fun `a second step answered with an empty pair is a failure`() {
        val state = AuthStateMapper.afterSecondStep(AuthResult.Ok(TokenResponse("", "r1", 900)), useRecovery = false)

        assertEquals(AuthUiState.Failed(AuthStateMapper.UNEXPECTED_KEY, retryable = false), state)
    }

    @Test
    fun `a refusal while using a recovery code stays in recovery mode`() {
        val state = AuthStateMapper.afterSecondStep(refused("mfa.code_wrong"), useRecovery = true)

        val step = assertIs<AuthUiState.SecondStep>(state)
        assertEquals(true, step.useRecovery)
        assertEquals("mfa.code_wrong", step.messageKey)
    }
}
