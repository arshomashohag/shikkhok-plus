package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.TokenResponse
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.auth.PasswordRules
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

/**
 * The signed-in password and contact screens' state machines: loading,
 * success, refusal, and the explicit retry of a failed write [TC-8, D-9].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class AccountViewModelsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun refused(key: String, retryable: Boolean = false, details: Map<String, String>? = null) =
        AuthResult.Refused(ErrorEnvelope(ErrorBody("X", retryable, key, details)))

    private val pair = TokenResponse("a.b.c", "r2", 900)

    private class FakeAccount(
        var passwordResult: AuthResult<TokenResponse> = AuthResult.Ok(TokenResponse("a.b.c", "r2", 900)),
        var requestResult: AuthResult<IssueResponse> = AuthResult.Ok(IssueResponse("requested")),
        var verifyResult: AuthResult<MeDto> = AuthResult.Ok(MeDto(phone = "+8801711111111")),
    ) : AccountRepository {
        val passwords = mutableListOf<Pair<String?, String>>()
        val requests = mutableListOf<Identifier>()
        val codes = mutableListOf<Pair<Identifier, String>>()

        override suspend fun setPassword(currentPassword: String?, newPassword: String): AuthResult<TokenResponse> {
            passwords += currentPassword to newPassword
            return passwordResult
        }

        override suspend fun requestContact(identifier: Identifier): AuthResult<IssueResponse> {
            requests += identifier
            return requestResult
        }

        override suspend fun verifyContact(identifier: Identifier, code: String): AuthResult<MeDto> {
            codes += identifier to code
            return verifyResult
        }
    }

    // --- The password ------------------------------------------------------------

    @Test
    fun `a first password is set without a current one`() = runTest(dispatcher) {
        val repo = FakeAccount()
        val model = PasswordChangeViewModel(repo, hasPassword = false)

        model.submit("", "correct horse", "correct horse")
        assertEquals(PasswordChangeUiState.Editing(hasPassword = false, saving = true), model.state.value)
        advanceUntilIdle()

        assertEquals(PasswordChangeUiState.Done, model.state.value)
        assertEquals(listOf<Pair<String?, String>>(null to "correct horse"), repo.passwords)
    }

    @Test
    fun `a change sends the current password, and asks for it first`() = runTest(dispatcher) {
        val repo = FakeAccount()
        val model = PasswordChangeViewModel(repo, hasPassword = true)

        model.submit("", "correct horse", "correct horse")
        assertEquals(
            PasswordChangeUiState.Editing(hasPassword = true, messageKey = AccountStateMapper.CURRENT_REQUIRED_KEY),
            model.state.value,
        )

        model.submit("old horse", "correct horse", "correct horse")
        advanceUntilIdle()

        assertEquals(PasswordChangeUiState.Done, model.state.value)
        assertEquals(listOf<Pair<String?, String>>("old horse" to "correct horse"), repo.passwords)
    }

    @Test
    fun `a short or mismatched password never reaches the network`() = runTest(dispatcher) {
        val repo = FakeAccount()
        val model = PasswordChangeViewModel(repo, hasPassword = false)

        model.submit("", "short", "short")
        assertEquals(
            PasswordChangeUiState.Editing(hasPassword = false, messageKey = PasswordRules.TOO_SHORT_KEY),
            model.state.value,
        )
        model.submit("", "correct horse", "correct horsE")
        assertEquals(
            PasswordChangeUiState.Editing(hasPassword = false, messageKey = PasswordRules.MISMATCH_KEY),
            model.state.value,
        )
        advanceUntilIdle()

        assertEquals(emptyList(), repo.passwords)
    }

    @Test
    fun `a wrong current password is the server's words, on the form`() = runTest(dispatcher) {
        val model = PasswordChangeViewModel(FakeAccount(passwordResult = refused("auth.password.current_wrong")), true)

        model.submit("guess", "correct horse", "correct horse")
        advanceUntilIdle()

        assertEquals(
            PasswordChangeUiState.Editing(hasPassword = true, messageKey = "auth.password.current_wrong"),
            model.state.value,
        )
    }

    @Test
    fun `a save with no answer is retried only when the person asks`() = runTest(dispatcher) {
        val repo = FakeAccount(passwordResult = AuthResult.TransportFailure)
        val model = PasswordChangeViewModel(repo, hasPassword = false)

        model.submit("", "correct horse", "correct horse")
        advanceUntilIdle()
        assertEquals(
            PasswordChangeUiState.Editing(
                hasPassword = false,
                messageKey = AccountStateMapper.OFFLINE_KEY,
                retryable = true,
            ),
            model.state.value,
        )
        assertEquals(1, repo.passwords.size, "the failure must not auto-retry")

        repo.passwordResult = AuthResult.Ok(pair)
        model.submit("", "correct horse", "correct horse")
        advanceUntilIdle()

        assertEquals(PasswordChangeUiState.Done, model.state.value)
        assertEquals(2, repo.passwords.size)
    }

    @Test
    fun `a second press while saving sends nothing more`() = runTest(dispatcher) {
        val repo = FakeAccount()
        val model = PasswordChangeViewModel(repo, hasPassword = false)

        model.submit("", "correct horse", "correct horse")
        model.submit("", "correct horse", "correct horse")
        advanceUntilIdle()

        assertEquals(1, repo.passwords.size)
    }

    @Test
    fun `a pair with a half missing is not treated as done`() {
        val form = PasswordChangeUiState.Editing(hasPassword = false, saving = true)

        assertEquals(
            PasswordChangeUiState.Editing(hasPassword = false, messageKey = AccountStateMapper.UNEXPECTED_KEY),
            AccountStateMapper.afterPassword(AuthResult.Ok(TokenResponse("a.b.c", "", 900)), form),
        )
    }

    // --- Adding a phone or an email --------------------------------------------------

    @Test
    fun `adding a phone sends a code, then the code, and is added`() = runTest(dispatcher) {
        val repo = FakeAccount()
        val model = AddContactViewModel(repo, IdentifierKind.PHONE)

        model.requestCode("01711111111")
        assertEquals(AddContactUiState.Entering(IdentifierKind.PHONE, sending = true), model.state.value)
        advanceUntilIdle()
        assertEquals(AddContactUiState.AwaitingCode(IdentifierKind.PHONE), model.state.value)

        model.submitCode("123456")
        assertEquals(AddContactUiState.AwaitingCode(IdentifierKind.PHONE, checking = true), model.state.value)
        advanceUntilIdle()

        assertEquals(AddContactUiState.Added(IdentifierKind.PHONE), model.state.value)
        assertEquals(listOf(Identifier.phone("01711111111")), repo.requests)
        assertEquals(listOf(Identifier.phone("01711111111") to "123456"), repo.codes)
    }

    @Test
    fun `an account that already has one is told so, on the field`() = runTest(dispatcher) {
        val repo = FakeAccount(requestResult = refused("account.contact.already_set"))
        val model = AddContactViewModel(repo, IdentifierKind.EMAIL)

        model.requestCode("rafi@example.com")
        advanceUntilIdle()

        assertEquals(
            AddContactUiState.Entering(IdentifierKind.EMAIL, messageKey = "account.contact.already_set"),
            model.state.value,
        )
    }

    @Test
    fun `a request with no answer is retried only when asked`() = runTest(dispatcher) {
        val repo = FakeAccount(requestResult = AuthResult.TransportFailure)
        val model = AddContactViewModel(repo, IdentifierKind.EMAIL)

        model.requestCode("rafi@example.com")
        advanceUntilIdle()
        assertEquals(
            AddContactUiState.Entering(
                IdentifierKind.EMAIL,
                messageKey = AccountStateMapper.OFFLINE_KEY,
                retryable = true,
            ),
            model.state.value,
        )
        assertEquals(1, repo.requests.size, "the failure must not auto-retry")

        repo.requestResult = AuthResult.Ok(IssueResponse("requested"))
        model.requestCode("rafi@example.com")
        advanceUntilIdle()

        assertEquals(AddContactUiState.AwaitingCode(IdentifierKind.EMAIL), model.state.value)
        assertEquals(2, repo.requests.size)
    }

    @Test
    fun `a number another account uses is refused on the code step`() = runTest(dispatcher) {
        val repo = FakeAccount(verifyResult = refused("account.contact.taken"))
        val model = AddContactViewModel(repo, IdentifierKind.PHONE)
        model.requestCode("01711111111")
        advanceUntilIdle()

        model.submitCode("123456")
        advanceUntilIdle()

        assertEquals(
            AddContactUiState.AwaitingCode(IdentifierKind.PHONE, messageKey = "account.contact.taken"),
            model.state.value,
        )
    }

    @Test
    fun `a wrong code carries the tries left, and the retry sends the code again`() = runTest(dispatcher) {
        val repo = FakeAccount(verifyResult = refused("auth.otp.wrong", details = mapOf("attempts_left" to "4")))
        val model = AddContactViewModel(repo, IdentifierKind.PHONE)
        model.requestCode("01711111111")
        advanceUntilIdle()

        model.submitCode("000000")
        advanceUntilIdle()
        assertEquals(
            AddContactUiState.AwaitingCode(IdentifierKind.PHONE, messageKey = "auth.otp.wrong", attemptsLeft = "4"),
            model.state.value,
        )

        repo.verifyResult = AuthResult.Ok(MeDto(phone = "+8801711111111"))
        model.submitCode("123456")
        advanceUntilIdle()

        assertEquals(AddContactUiState.Added(IdentifierKind.PHONE), model.state.value)
        assertEquals(2, repo.codes.size)
    }

    @Test
    fun `a code check with no answer stays on the code step with a retry`() = runTest(dispatcher) {
        val model = AddContactViewModel(FakeAccount(verifyResult = AuthResult.TransportFailure), IdentifierKind.PHONE)
        model.requestCode("01711111111")
        advanceUntilIdle()

        model.submitCode("123456")
        advanceUntilIdle()

        assertEquals(
            AddContactUiState.AwaitingCode(
                IdentifierKind.PHONE,
                messageKey = AccountStateMapper.OFFLINE_KEY,
                retryable = true,
            ),
            model.state.value,
        )
    }

    @Test
    fun `a new code keeps the code step on screen and goes to the same number`() = runTest(dispatcher) {
        val repo = FakeAccount()
        val model = AddContactViewModel(repo, IdentifierKind.PHONE)
        model.requestCode("01711111111")
        advanceUntilIdle()

        model.resendCode()
        assertEquals(AddContactUiState.AwaitingCode(IdentifierKind.PHONE, checking = true), model.state.value)
        advanceUntilIdle()

        assertEquals(AddContactUiState.AwaitingCode(IdentifierKind.PHONE), model.state.value)
        assertEquals(listOf(Identifier.phone("01711111111"), Identifier.phone("01711111111")), repo.requests)
    }

    @Test
    fun `changing the value goes back to the field and forgets where the code went`() = runTest(dispatcher) {
        val repo = FakeAccount()
        val model = AddContactViewModel(repo, IdentifierKind.EMAIL)
        model.requestCode("rafi@example.com")
        advanceUntilIdle()

        model.changeValue()
        model.submitCode("123456")
        model.resendCode()
        advanceUntilIdle()

        assertEquals(AddContactUiState.Entering(IdentifierKind.EMAIL), model.state.value)
        assertEquals(emptyList(), repo.codes)
        assertEquals(1, repo.requests.size)
    }

    @Test
    fun `a code request answered with nothing is a retryable failure on the field`() {
        val form = AddContactUiState.Entering(IdentifierKind.PHONE, sending = true)

        assertEquals(
            AddContactUiState.Entering(
                IdentifierKind.PHONE,
                messageKey = AccountStateMapper.UNEXPECTED_KEY,
                retryable = true,
            ),
            AccountStateMapper.afterContactRequested(AuthResult.Ok(IssueResponse("")), form),
        )
    }

    @Test
    fun `a refused or unanswered resend stays on the code step, with no retry of the code`() {
        val step = AddContactUiState.AwaitingCode(IdentifierKind.EMAIL, checking = true, attemptsLeft = "2")

        assertEquals(
            AddContactUiState.AwaitingCode(IdentifierKind.EMAIL, messageKey = "auth.otp.temporarily_unavailable"),
            AccountStateMapper.afterContactResent(refused("auth.otp.temporarily_unavailable", retryable = true), step),
        )
        assertEquals(
            AddContactUiState.AwaitingCode(IdentifierKind.EMAIL, messageKey = AccountStateMapper.OFFLINE_KEY),
            AccountStateMapper.afterContactResent(AuthResult.TransportFailure, step),
        )
    }

    @Test
    fun `a password request never prints either password`() {
        val printed =
            com.shikkhokplus.app.core.network.MePasswordRequest("old horse", "correct horse").toString()

        kotlin.test.assertFalse("old horse" in printed || "correct horse" in printed)
    }
}
