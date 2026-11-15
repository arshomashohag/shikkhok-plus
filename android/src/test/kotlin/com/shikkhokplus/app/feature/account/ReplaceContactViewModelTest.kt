package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.model.Identifier
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.feature.account.FakeAccountRepository.Companion.refused
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

/**
 * The replace flow (functional-spec 3.6) [FR8.2; NFR3.4]: each request
 * refusal routed, the code step, each verify refusal, the tries left,
 * Replaced, a new code that asks for the password again, and the retry.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ReplaceContactViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val sent = AuthResult.Ok(IssueResponse("requested"))

    private fun atCode(repository: FakeAccountRepository): ReplaceContactViewModel {
        repository.replaceAnswers += sent
        val model = ReplaceContactViewModel(repository, IdentifierKind.PHONE)
        model.requestCode("01811223344", "correct horse")
        return model
    }

    @Test
    fun `the request carries the new value and the password, once`() = runTest(dispatcher) {
        val repository = FakeAccountRepository().apply { replaceAnswers += sent }
        val model = ReplaceContactViewModel(repository, IdentifierKind.PHONE)

        model.requestCode("01811223344", "correct horse")
        model.requestCode("01811223344", "correct horse")
        assertEquals(ReplaceContactUiState.Entering(IdentifierKind.PHONE, sending = true), model.state.value)
        advanceUntilIdle()

        assertEquals(ReplaceContactUiState.AwaitingCode(IdentifierKind.PHONE), model.state.value)
        assertEquals(listOf(Identifier.phone("01811223344") to "correct horse"), repository.replacements)
    }

    @Test
    fun `each request refusal is routed to its place`() = runTest(dispatcher) {
        val expected =
            mapOf(
                "account.contact.password_required" to
                    ReplaceContactUiState.Entering(
                        IdentifierKind.PHONE,
                        bannerKey = "account.contact.password_required",
                        offerSetPassword = true,
                    ),
                "auth.password.current_wrong" to
                    ReplaceContactUiState.Entering(IdentifierKind.PHONE, passwordKey = "auth.password.current_wrong"),
                "account.contact.already_set" to
                    ReplaceContactUiState.Entering(IdentifierKind.PHONE, valueKey = "account.contact.already_set"),
                "account.contact.admin_locked" to
                    ReplaceContactUiState.Entering(IdentifierKind.PHONE, bannerKey = "account.contact.admin_locked"),
                "account.contact.change_limit" to
                    ReplaceContactUiState.Entering(IdentifierKind.PHONE, bannerKey = "account.contact.change_limit"),
            )
        expected.forEach { (key, state) ->
            val repository = FakeAccountRepository().apply { replaceAnswers += refused(key) }
            val model = ReplaceContactViewModel(repository, IdentifierKind.PHONE)

            model.requestCode("01811223344", "correct horse")
            advanceUntilIdle()

            assertEquals(state, model.state.value, key)
        }
    }

    @Test
    fun `a lost request offers a retry that resends the same request`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply {
                replaceAnswers += AuthResult.TransportFailure
                replaceAnswers += sent
            }
        val model = ReplaceContactViewModel(repository, IdentifierKind.EMAIL)
        model.requestCode("new@example.com", "correct horse")
        advanceUntilIdle()
        assertEquals(
            ReplaceContactUiState.Entering(
                IdentifierKind.EMAIL,
                bannerKey = ReplaceContactStateMapper.OFFLINE_KEY,
                retryable = true,
            ),
            model.state.value,
        )

        model.requestCode("new@example.com", "correct horse")
        advanceUntilIdle()

        assertEquals(2, repository.replacements.size)
        assertEquals(repository.replacements[0], repository.replacements[1])
        assertEquals(ReplaceContactUiState.AwaitingCode(IdentifierKind.EMAIL), model.state.value)
    }

    @Test
    fun `the code goes to the new value, and a 200 is Replaced`() = runTest(dispatcher) {
        val repository = FakeAccountRepository()
        val model = atCode(repository)
        advanceUntilIdle()
        repository.verifyAnswers += AuthResult.Ok(MeDto(phone = "+8801811223344"))

        model.submitCode("123456")
        advanceUntilIdle()

        assertEquals(listOf(Identifier.phone("01811223344") to "123456"), repository.verifications)
        assertEquals(ReplaceContactUiState.Replaced(IdentifierKind.PHONE), model.state.value)
    }

    @Test
    fun `taken and change-limit stay on the code step, and a wrong code shows the tries left`() =
        runTest(dispatcher) {
            val repository = FakeAccountRepository()
            val model = atCode(repository)
            advanceUntilIdle()
            repository.verifyAnswers += refused("account.contact.taken")
            repository.verifyAnswers += refused("account.contact.change_limit")
            repository.verifyAnswers += refused("auth.otp.wrong", details = mapOf("attempts_left" to "2"))

            model.submitCode("111111")
            advanceUntilIdle()
            assertEquals(
                ReplaceContactUiState.AwaitingCode(IdentifierKind.PHONE, messageKey = "account.contact.taken"),
                model.state.value,
            )
            model.submitCode("222222")
            advanceUntilIdle()
            assertEquals(
                "account.contact.change_limit",
                (model.state.value as ReplaceContactUiState.AwaitingCode).messageKey,
            )
            model.submitCode("333333")
            advanceUntilIdle()

            assertEquals(
                ReplaceContactUiState.AwaitingCode(
                    IdentifierKind.PHONE,
                    messageKey = "auth.otp.wrong",
                    attemptsLeft = "2",
                ),
                model.state.value,
            )
        }

    @Test
    fun `a lost code check is retryable with the same code`() = runTest(dispatcher) {
        val repository = FakeAccountRepository()
        val model = atCode(repository)
        advanceUntilIdle()
        repository.verifyAnswers += AuthResult.TransportFailure
        repository.verifyAnswers += AuthResult.Ok(MeDto())

        model.submitCode("123456")
        advanceUntilIdle()
        assertEquals(true, (model.state.value as ReplaceContactUiState.AwaitingCode).retryable)
        model.submitCode("123456")
        advanceUntilIdle()

        assertEquals(listOf("123456", "123456"), repository.verifications.map { it.second })
        assertEquals(ReplaceContactUiState.Replaced(IdentifierKind.PHONE), model.state.value)
    }

    @Test
    fun `a new code goes back to the entry step, where the password is asked again`() = runTest(dispatcher) {
        val repository = FakeAccountRepository()
        val model = atCode(repository)
        advanceUntilIdle()

        model.changeValue()
        model.submitCode("123456")
        advanceUntilIdle()

        assertEquals(ReplaceContactUiState.Entering(IdentifierKind.PHONE), model.state.value)
        assertEquals(emptyList(), repository.verifications, "no code is sent from the entry step")
        assertEquals(1, repository.replacements.size, "the password was used once and not kept for a resend")
    }
}
