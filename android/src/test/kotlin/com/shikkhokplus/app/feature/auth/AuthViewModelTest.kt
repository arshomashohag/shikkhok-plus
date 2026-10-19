package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse
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
import kotlin.test.assertTrue

/**
 * The ViewModel's own state machine, driven through the coroutine.
 *
 * [AuthStateMapperTest] covers the mapping decisions; this file covers
 * the parts only the ViewModel has — the loading state, and the
 * **explicit retry path** that [TC-8, D-9] require because V1 accepts
 * no write without connectivity and has no local queue.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private class FakeRepository(
        var issueResult: AuthResult<IssueResponse> =
            AuthResult.Ok(IssueResponse("requested")),
        var verifyResult: AuthResult<TokenResponse> =
            AuthResult.Ok(TokenResponse("a.b.c", "opaque", 900)),
    ) : AuthRepository {
        var issueCalls = 0
        var verifyCalls = 0

        override suspend fun issue(phone: String): AuthResult<IssueResponse> {
            issueCalls++
            return issueResult
        }

        override suspend fun verify(
            phone: String,
            code: String,
        ): AuthResult<TokenResponse> {
            verifyCalls++
            return verifyResult
        }
    }

    @Test
    fun `it starts idle`() {
        val model = AuthViewModel(FakeRepository())
        assertIs<AuthUiState.Idle>(model.state.value)
    }

    @Test
    fun `requesting a code shows the loading state first`() = runTest {
        val model = AuthViewModel(FakeRepository())
        model.requestCode("+8801711111111")
        assertIs<AuthUiState.Sending>(model.state.value)

        advanceUntilIdle()
        assertIs<AuthUiState.AwaitingCode>(model.state.value)
    }

    @Test
    fun `a successful verify reaches signed in`() = runTest {
        val model = AuthViewModel(FakeRepository())
        model.requestCode("+8801711111111")
        advanceUntilIdle()

        model.submitCode("123456")
        advanceUntilIdle()
        assertIs<AuthUiState.SignedIn>(model.state.value)
    }

    @Test
    fun `a transport failure surfaces an explicit retry`() = runTest {
        // THE RETRY PATH. No local queue and no silent retry: the user
        // is shown the failure and asks for the retry themselves.
        val repository = FakeRepository(issueResult = AuthResult.TransportFailure)
        val model = AuthViewModel(repository)

        model.requestCode("+8801711111111")
        advanceUntilIdle()

        val failed = assertIs<AuthUiState.Failed>(model.state.value)
        assertTrue(failed.retryable)
        assertEquals(1, repository.issueCalls, "the failure must not auto-retry")
    }

    @Test
    fun `retry re-runs the last action only when the user asks`() = runTest {
        val repository = FakeRepository(issueResult = AuthResult.TransportFailure)
        val model = AuthViewModel(repository)

        model.requestCode("+8801711111111")
        advanceUntilIdle()
        assertEquals(1, repository.issueCalls)

        repository.issueResult = AuthResult.Ok(IssueResponse("requested"))
        model.retry()
        advanceUntilIdle()

        assertEquals(2, repository.issueCalls)
        assertIs<AuthUiState.AwaitingCode>(model.state.value)
    }

    @Test
    fun `retry does nothing when the server said not retryable`() = runTest {
        // Retryability is the SERVER's call [TC-9]. A ceiling breach is
        // not retryable, and retrying into a cost ceiling is exactly
        // the thing the ceiling exists to prevent.
        val repository = FakeRepository(
            issueResult = AuthResult.Refused(
                ErrorEnvelope(
                    ErrorBody(
                        code = "TEMPORARILY_UNAVAILABLE",
                        retryable = false,
                        messageKey = "auth.otp.temporarily_unavailable",
                    ),
                ),
            ),
        )
        val model = AuthViewModel(repository)

        model.requestCode("+8801711111111")
        advanceUntilIdle()
        assertEquals(1, repository.issueCalls)

        model.retry()
        advanceUntilIdle()
        assertEquals(1, repository.issueCalls, "a non-retryable failure must not re-send")
    }

    @Test
    fun `retry does nothing from a non failed state`() = runTest {
        val repository = FakeRepository()
        val model = AuthViewModel(repository)

        model.requestCode("+8801711111111")
        advanceUntilIdle()

        model.retry()
        advanceUntilIdle()
        assertEquals(1, repository.issueCalls)
    }

    @Test
    fun `a refused verify does not reach signed in`() = runTest {
        val repository = FakeRepository(
            verifyResult = AuthResult.Refused(
                ErrorEnvelope(
                    ErrorBody("OTP_NOT_VALID", false, "auth.otp.not_valid"),
                ),
            ),
        )
        val model = AuthViewModel(repository)

        model.requestCode("+8801711111111")
        advanceUntilIdle()
        model.submitCode("000000")
        advanceUntilIdle()

        val failed = assertIs<AuthUiState.Failed>(model.state.value)
        assertEquals("auth.otp.not_valid", failed.messageKey)
    }

    @Test
    fun `the view model holds no business logic of its own`() {
        // Every decision is delegated to AuthStateMapper. If this file
        // grew a comparison on a domain value, that would be a business
        // rule on the client [TC-9, D-31].
        val source = java.io.File(
            "src/main/kotlin/com/shikkhokplus/app/feature/auth/AuthViewModel.kt",
        ).readText()
        val body = source.substringAfter("class AuthViewModel")
        assertTrue(
            Regex("""\b(if|when)\s*\([^)]*[<>]=?""").findAll(body).none(),
            "a comparison on a domain value appeared in the ViewModel",
        )
    }
}
