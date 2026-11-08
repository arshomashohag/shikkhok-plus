package com.shikkhokplus.app.feature.auth

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.core.network.VerifyResponse
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
 * the parts only the ViewModel has — the loading states, the secrets it
 * holds between steps, and the **explicit retry path** that [TC-8, D-9]
 * require because V1 accepts no write without connectivity and has no
 * local queue.
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

    private val phone = Identifier.phone("+8801711111111")

    private val pair = TokenResponse("a.b.c", "opaque", 900)

    private fun refused(key: String, retryable: Boolean = false) =
        AuthResult.Refused(ErrorEnvelope(ErrorBody(code = "X", retryable = retryable, messageKey = key)))

    /** One setup the fake was asked for. */
    private data class Setup(val token: String, val password: String, val code: String?, val recovery: String?)

    private class FakeRepository(
        var issueResult: AuthResult<IssueResponse> = AuthResult.Ok(IssueResponse("requested")),
        var verifyResult: AuthResult<VerifyResponse> =
            AuthResult.Ok(VerifyResponse(passwordSetupToken = "setup", passwordSetupExpiresIn = 600)),
        var signInResult: AuthResult<VerifyResponse> = AuthResult.Ok(VerifyResponse("a.b.c", "opaque", 900)),
        var setupResult: AuthResult<TokenResponse> = AuthResult.Ok(TokenResponse("a.b.c", "opaque", 900)),
    ) : AuthRepository {
        var issueCalls = 0
        var verifyCalls = 0
        var signInCalls = 0
        val issued = mutableListOf<Identifier>()
        val setups = mutableListOf<Setup>()

        override suspend fun issue(identifier: Identifier): AuthResult<IssueResponse> {
            issueCalls++
            issued += identifier
            return issueResult
        }

        override suspend fun verify(identifier: Identifier, code: String): AuthResult<VerifyResponse> {
            verifyCalls++
            return verifyResult
        }

        override suspend fun signIn(identifier: Identifier, password: String): AuthResult<VerifyResponse> {
            signInCalls++
            return signInResult
        }

        override suspend fun setupPassword(
            token: String,
            password: String,
            code: String?,
            recoveryCode: String?,
        ): AuthResult<TokenResponse> {
            setups += Setup(token, password, code, recoveryCode)
            return setupResult
        }

        override suspend fun verifySecondStep(
            challenge: String,
            code: String?,
            recoveryCode: String?,
        ): AuthResult<TokenResponse> = AuthResult.TransportFailure
    }

    // --- Starting up -------------------------------------------------------

    @Test
    fun `the first state is Restoring, not Idle`() {
        // **The defect this fixes, reported from a device.** `Idle`
        // meant both "never signed in" and "still checking", so the
        // graph started at the sign-in screen and jumped to the home
        // screen a second or two later.
        val model = AuthViewModel(FakeRepository())

        assertEquals(AuthUiState.Restoring, model.state.value)
    }

    @Test
    fun `a restored session resolves to SignedIn`() = runTest(dispatcher) {
        val model = AuthViewModel(FakeRepository())

        model.resumeSession { SessionResume.RENEWED }
        advanceUntilIdle()

        assertEquals(AuthUiState.SignedIn, model.state.value)
    }

    @Test
    fun `an offline cold start stays signed in rather than asking for a password`() = runTest(dispatcher) {
        val model = AuthViewModel(FakeRepository())

        model.resumeSession { SessionResume.UNVERIFIED }
        advanceUntilIdle()

        assertEquals(AuthUiState.SignedIn, model.state.value)
    }

    @Test
    fun `an ended session resolves to the sign-in form, silently and without hanging`() = runTest(dispatcher) {
        val model = AuthViewModel(FakeRepository())

        model.resumeSession { SessionResume.ENDED }
        advanceUntilIdle()

        assertEquals(AuthUiState.Idle, model.state.value)
    }

    // --- Signing in with a password -----------------------------------------

    @Test
    fun `a password sign-in shows the loading state, then signs in`() = runTest(dispatcher) {
        val model = AuthViewModel(FakeRepository())

        model.signIn(phone, "correct horse")
        assertEquals(AuthUiState.SigningIn, model.state.value)

        advanceUntilIdle()
        assertEquals(AuthUiState.SignedIn, model.state.value)
    }

    @Test
    fun `a wrong password stays on the form and offers the code flow`() = runTest(dispatcher) {
        val repository = FakeRepository(signInResult = refused("auth.password.wrong"))
        val model = AuthViewModel(repository)

        model.signIn(Identifier.email("rafi@example.com"), "wrong one")
        advanceUntilIdle()

        assertEquals(
            AuthUiState.Failed("auth.password.wrong", retryable = false, offerCodeFlow = true),
            model.state.value,
        )
    }

    @Test
    fun `a sign-in that cannot reach the server is retried once, and only when asked`() = runTest(dispatcher) {
        val repository = FakeRepository(signInResult = AuthResult.TransportFailure)
        val model = AuthViewModel(repository)

        model.signIn(phone, "correct horse")
        advanceUntilIdle()
        val failed = assertIs<AuthUiState.Failed>(model.state.value)
        assertTrue(failed.retryable)
        assertEquals(1, repository.signInCalls, "the failure must not auto-retry")

        repository.signInResult = AuthResult.Ok(VerifyResponse("a.b.c", "opaque", 900))
        model.retry()
        advanceUntilIdle()

        assertEquals(2, repository.signInCalls)
        assertEquals(AuthUiState.SignedIn, model.state.value)
    }

    @Test
    fun `a refused sign-in is not retried, even when retry is pressed`() = runTest(dispatcher) {
        val repository = FakeRepository(signInResult = refused("auth.password.too_many_attempts"))
        val model = AuthViewModel(repository)

        model.signIn(phone, "correct horse")
        advanceUntilIdle()
        model.retry()
        advanceUntilIdle()

        assertEquals(1, repository.signInCalls)
    }

    @Test
    fun `an account with two-step verification goes to the second step after its password`() =
        runTest(dispatcher) {
            val repository =
                FakeRepository(signInResult = AuthResult.Ok(VerifyResponse(mfaRequired = true, mfaChallenge = "chal")))
            val model = AuthViewModel(repository)

            model.signIn(phone, "correct horse")
            advanceUntilIdle()

            assertEquals(AuthUiState.SecondStep(), model.state.value)
        }

    // --- The code flow -------------------------------------------------------

    @Test
    fun `the code flow opens on its own first step and sends nothing`() {
        val repository = FakeRepository()
        val model = AuthViewModel(repository)

        model.startCodeFlow()

        assertEquals(AuthUiState.CodeFlowStart, model.state.value)
        assertEquals(0, repository.issueCalls)
    }

    @Test
    fun `requesting a code shows the loading state first, and says where it went`() = runTest(dispatcher) {
        val model = AuthViewModel(FakeRepository())

        model.requestCode(Identifier.email("rafi@example.com"))
        assertEquals(AuthUiState.Sending, model.state.value)
        assertEquals(IdentifierKind.EMAIL, model.codeDestination.value)

        advanceUntilIdle()
        assertEquals(AuthUiState.AwaitingCode, model.state.value)
    }

    @Test
    fun `a failed code request stays on the code flow's first step, with a retry`() = runTest(dispatcher) {
        val repository = FakeRepository(issueResult = AuthResult.TransportFailure)
        val model = AuthViewModel(repository)

        model.requestCode(phone)
        advanceUntilIdle()
        assertEquals(
            AuthUiState.Failed(AuthStateMapper.OFFLINE_KEY, retryable = true, step = AuthStep.CODE_REQUEST),
            model.state.value,
        )
        assertEquals(1, repository.issueCalls, "the failure must not auto-retry")

        repository.issueResult = AuthResult.Ok(IssueResponse("requested"))
        model.retry()
        advanceUntilIdle()

        assertEquals(2, repository.issueCalls)
        assertEquals(AuthUiState.AwaitingCode, model.state.value)
    }

    @Test
    fun `retry does nothing when the server said not retryable`() = runTest(dispatcher) {
        // Retryability is the SERVER's call [TC-9]: retrying into a cost
        // ceiling is exactly what the ceiling exists to prevent.
        val repository = FakeRepository(issueResult = refused("auth.otp.temporarily_unavailable"))
        val model = AuthViewModel(repository)

        model.requestCode(phone)
        advanceUntilIdle()
        model.retry()
        advanceUntilIdle()

        assertEquals(1, repository.issueCalls, "a non-retryable failure must not re-send")
    }

    @Test
    fun `a verified code asks for a password, and creates no session yet`() = runTest(dispatcher) {
        val repository = FakeRepository()
        val model = AuthViewModel(repository)
        model.requestCode(phone)
        advanceUntilIdle()

        model.submitCode("123456")
        assertEquals(AuthUiState.CheckingCode, model.state.value)
        advanceUntilIdle()

        assertEquals(AuthUiState.ChoosePassword(mfaRequired = false), model.state.value)
        assertEquals(emptyList(), repository.setups, "nothing is set before a password is chosen")
    }

    @Test
    fun `a refused code stays on the code screen with the tries left`() = runTest(dispatcher) {
        val repository =
            FakeRepository(
                verifyResult =
                    AuthResult.Refused(
                        ErrorEnvelope(
                            ErrorBody("OTP_NOT_VALID", false, "auth.otp.wrong", mapOf("attempts_left" to "3")),
                        ),
                    ),
            )
        val model = AuthViewModel(repository)
        model.requestCode(phone)
        advanceUntilIdle()

        model.submitCode("000000")
        advanceUntilIdle()

        assertEquals(
            AuthUiState.CodeRejected("auth.otp.wrong", retryable = false, attemptsLeft = "3"),
            model.state.value,
        )
    }

    @Test
    fun `a code that cannot reach the server stays on the code screen with a retry`() = runTest(dispatcher) {
        val model = AuthViewModel(FakeRepository(verifyResult = AuthResult.TransportFailure))
        model.requestCode(phone)
        advanceUntilIdle()

        model.submitCode("123456")
        advanceUntilIdle()

        val rejected = assertIs<AuthUiState.CodeRejected>(model.state.value)
        assertTrue(rejected.retryable)
    }

    @Test
    fun `choosing a password sends it with the setup token and signs in`() = runTest(dispatcher) {
        val repository = FakeRepository()
        val model = AuthViewModel(repository)
        model.requestCode(phone)
        advanceUntilIdle()
        model.submitCode("123456")
        advanceUntilIdle()

        model.choosePassword("correct horse", "correct horse")
        assertEquals(AuthUiState.ChoosePassword(checking = true), model.state.value)
        advanceUntilIdle()

        assertEquals(AuthUiState.SignedIn, model.state.value)
        assertEquals(listOf(Setup("setup", "correct horse", null, null)), repository.setups)
    }

    @Test
    fun `a short or mismatched password is refused here and never sent`() = runTest(dispatcher) {
        val repository = FakeRepository()
        val model = AuthViewModel(repository)
        model.requestCode(phone)
        advanceUntilIdle()
        model.submitCode("123456")
        advanceUntilIdle()

        model.choosePassword("short", "short")
        assertEquals(AuthUiState.ChoosePassword(messageKey = PasswordRules.TOO_SHORT_KEY), model.state.value)

        model.choosePassword("correct horse", "correct horsE")
        assertEquals(AuthUiState.ChoosePassword(messageKey = PasswordRules.MISMATCH_KEY), model.state.value)

        advanceUntilIdle()
        assertEquals(emptyList(), repository.setups)
    }

    @Test
    fun `a password the server finds too common stays on the form to choose again`() = runTest(dispatcher) {
        val repository = FakeRepository(setupResult = refused("auth.password.too_common"))
        val model = AuthViewModel(repository)
        model.requestCode(phone)
        advanceUntilIdle()
        model.submitCode("123456")
        advanceUntilIdle()

        model.choosePassword("password1", "password1")
        advanceUntilIdle()
        assertEquals(AuthUiState.ChoosePassword(messageKey = "auth.password.too_common"), model.state.value)

        // The token is still good for a second choice.
        repository.setupResult = AuthResult.Ok(pair)
        model.choosePassword("correct horse", "correct horse")
        advanceUntilIdle()
        assertEquals(AuthUiState.SignedIn, model.state.value)
        assertEquals(listOf("setup", "setup"), repository.setups.map { it.token })
    }

    @Test
    fun `a setup that cannot reach the server is retried only when the person asks`() = runTest(dispatcher) {
        val repository = FakeRepository(setupResult = AuthResult.TransportFailure)
        val model = AuthViewModel(repository)
        model.requestCode(phone)
        advanceUntilIdle()
        model.submitCode("123456")
        advanceUntilIdle()

        model.choosePassword("correct horse", "correct horse")
        advanceUntilIdle()
        assertEquals(
            AuthUiState.ChoosePassword(messageKey = AuthStateMapper.OFFLINE_KEY, retryable = true),
            model.state.value,
        )
        assertEquals(1, repository.setups.size, "the failure must not auto-retry")

        // THE RETRY: the screen sends what is still typed.
        repository.setupResult = AuthResult.Ok(pair)
        model.choosePassword("correct horse", "correct horse")
        advanceUntilIdle()

        assertEquals(AuthUiState.SignedIn, model.state.value)
        assertEquals(2, repository.setups.size)
    }

    @Test
    fun `a lapsed setup token goes back to the code flow's start and is forgotten`() = runTest(dispatcher) {
        val repository = FakeRepository(setupResult = refused("auth.password.setup_expired", retryable = true))
        val model = AuthViewModel(repository)
        model.requestCode(phone)
        advanceUntilIdle()
        model.submitCode("123456")
        advanceUntilIdle()

        model.choosePassword("correct horse", "correct horse")
        advanceUntilIdle()

        assertEquals(
            AuthUiState.Failed("auth.password.setup_expired", retryable = false, step = AuthStep.CODE_REQUEST),
            model.state.value,
        )
        model.choosePassword("correct horse", "correct horse")
        model.retry()
        advanceUntilIdle()
        assertEquals(1, repository.setups.size)
    }

    @Test
    fun `an account with two-step verification sends the app code, or a recovery code`() = runTest(dispatcher) {
        val repository =
            FakeRepository(
                verifyResult = AuthResult.Ok(VerifyResponse(mfaRequired = true, passwordSetupToken = "setup")),
                setupResult = refused("mfa.code_wrong"),
            )
        val model = AuthViewModel(repository)
        model.requestCode(phone)
        advanceUntilIdle()
        model.submitCode("123456")
        advanceUntilIdle()
        assertEquals(AuthUiState.ChoosePassword(mfaRequired = true), model.state.value)

        model.choosePassword("correct horse", "correct horse", "654321")
        advanceUntilIdle()
        assertEquals(
            AuthUiState.ChoosePassword(mfaRequired = true, messageKey = "mfa.code_wrong"),
            model.state.value,
        )

        model.toggleSetupRecoveryCode()
        assertEquals(AuthUiState.ChoosePassword(mfaRequired = true, useRecovery = true), model.state.value)
        repository.setupResult = AuthResult.Ok(pair)
        model.choosePassword("correct horse", "correct horse", "ABCDE-FGHJK")
        advanceUntilIdle()

        assertEquals(AuthUiState.SignedIn, model.state.value)
        assertEquals(
            listOf(
                Setup("setup", "correct horse", "654321", null),
                Setup("setup", "correct horse", null, "ABCDE-FGHJK"),
            ),
            repository.setups,
        )
    }

    @Test
    fun `the recovery switch is not offered to an account without two-step verification`() = runTest(dispatcher) {
        val model = AuthViewModel(FakeRepository())
        model.requestCode(phone)
        advanceUntilIdle()
        model.submitCode("123456")
        advanceUntilIdle()

        model.toggleSetupRecoveryCode()

        assertEquals(AuthUiState.ChoosePassword(), model.state.value)
    }

    @Test
    fun `a new code goes to the same identifier, and only when asked`() = runTest(dispatcher) {
        val repository = FakeRepository()
        val model = AuthViewModel(repository)

        model.requestCode(Identifier.email("rafi@example.com"))
        advanceUntilIdle()
        model.resendCode()
        advanceUntilIdle()

        assertEquals(2, repository.issueCalls)
        assertEquals(listOf("rafi@example.com", "rafi@example.com"), repository.issued.map { it.value })
        assertEquals(AuthUiState.AwaitingCode, model.state.value)
    }

    @Test
    fun `changing the identifier returns to the code flow's start and sends nothing`() = runTest(dispatcher) {
        val repository = FakeRepository()
        val model = AuthViewModel(repository)
        model.requestCode(phone)
        advanceUntilIdle()

        model.changeNumber()

        assertEquals(AuthUiState.CodeFlowStart, model.state.value)
        assertEquals(1, repository.issueCalls)
    }

    // --- After sign-up ---------------------------------------------------------

    @Test
    fun `after sign-up the chosen password is set as soon as the code is verified`() = runTest(dispatcher) {
        val repository = FakeRepository()
        val model = AuthViewModel(repository)

        model.adoptPendingCode(Identifier.email("rafi@example.com"), "correct horse")
        assertEquals(AuthUiState.AwaitingCode, model.state.value)
        assertEquals(IdentifierKind.EMAIL, model.codeDestination.value)

        model.submitCode("123456")
        advanceUntilIdle()

        assertEquals(AuthUiState.SignedIn, model.state.value)
        assertEquals(listOf(Setup("setup", "correct horse", null, null)), repository.setups)
    }

    @Test
    fun `a sign-up password the server refuses is dropped, and a new one is asked for`() = runTest(dispatcher) {
        val repository = FakeRepository(setupResult = refused("auth.password.too_common"))
        val model = AuthViewModel(repository)
        model.adoptPendingCode(phone, "password1")

        model.submitCode("123456")
        advanceUntilIdle()
        assertEquals(AuthUiState.ChoosePassword(messageKey = "auth.password.too_common"), model.state.value)

        // A new code for the same sign-up does not resend the dropped
        // password: the held copy was spent on the first setup.
        model.changeNumber()
        model.adoptPendingCode(phone)
        model.submitCode("654321")
        advanceUntilIdle()
        assertEquals(1, repository.setups.size)
        assertEquals(AuthUiState.ChoosePassword(), model.state.value)
    }

    @Test
    fun `signing out returns to the sign-in form`() = runTest(dispatcher) {
        val model = AuthViewModel(FakeRepository())
        model.signIn(phone, "correct horse")
        advanceUntilIdle()

        model.signOut()

        assertEquals(AuthUiState.Idle, model.state.value)
    }

    @Test
    fun `the view model holds no business logic of its own`() {
        // Every decision is delegated to AuthStateMapper. If this file
        // grew a comparison on a domain value, that would be a business
        // rule on the client [TC-9, D-31].
        val source =
            java.io.File(
                "src/main/kotlin/com/shikkhokplus/app/feature/auth/AuthViewModel.kt",
            ).readText()
        val body = source.substringAfter("class AuthViewModel")
        assertTrue(
            Regex("""\b(if|when)\s*\([^)]*[<>]=?""").findAll(body).none(),
            "a comparison on a domain value appeared in the ViewModel",
        )
    }
}
