package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.model.IdentifierKind
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
import kotlin.test.assertFalse

/**
 * The remove sheet (functional-spec 3.6) [FR8.4; NFR3.11]: removed, the
 * last one refused by the server with a way to add the other, the other
 * refusals, and the retry of a lost removal.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class RemoveContactViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun model(repository: FakeAccountRepository) =
        RemoveContactViewModel(repository, IdentifierKind.EMAIL, "rafi@example.com")

    private val confirming = RemoveContactUiState.Confirming(IdentifierKind.EMAIL, "rafi@example.com")

    @Test
    fun `a 200 is Removed, after one request with the kind and the password`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply { removeAnswers += AuthResult.Ok(MeDto(phone = "+8801711111111")) }
        val model = model(repository)

        model.remove("correct horse")
        model.remove("correct horse")
        assertEquals(confirming.copy(removing = true), model.state.value)
        advanceUntilIdle()

        assertEquals(RemoveContactUiState.Removed, model.state.value)
        assertEquals(listOf(IdentifierKind.EMAIL to "correct horse"), repository.removals)
    }

    @Test
    fun `the last one is refused in the sheet, offering the other kind`() = runTest(dispatcher) {
        val repository = FakeAccountRepository().apply { removeAnswers += refused("account.contact.last_one") }
        val model = model(repository)

        model.remove("correct horse")
        advanceUntilIdle()

        assertEquals(confirming.copy(bannerKey = "account.contact.last_one", offerAddOther = true), model.state.value)
    }

    @Test
    fun `a wrong password goes under the password, and no password yet offers one`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply {
                removeAnswers += refused("auth.password.current_wrong")
                removeAnswers += refused("account.contact.password_required")
            }
        val model = model(repository)

        model.remove("wrong one")
        advanceUntilIdle()
        assertEquals(confirming.copy(passwordKey = "auth.password.current_wrong"), model.state.value)

        model.remove("anything")
        advanceUntilIdle()
        assertEquals(
            confirming.copy(bannerKey = "account.contact.password_required", offerSetPassword = true),
            model.state.value,
        )
    }

    @Test
    fun `a lost removal offers a retry that resends the same kind and password`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply {
                removeAnswers += AuthResult.TransportFailure
                removeAnswers += AuthResult.Ok(MeDto())
            }
        val model = model(repository)

        model.remove("correct horse")
        advanceUntilIdle()
        assertEquals(
            confirming.copy(bannerKey = RemoveContactStateMapper.OFFLINE_KEY, retryable = true),
            model.state.value,
        )
        model.remove("correct horse")
        advanceUntilIdle()

        assertEquals(
            listOf(IdentifierKind.EMAIL to "correct horse", IdentifierKind.EMAIL to "correct horse"),
            repository.removals,
        )
        assertEquals(RemoveContactUiState.Removed, model.state.value)
    }

    @Test
    fun `too many attempts and the change limit are banners, not retryable`() = runTest(dispatcher) {
        val keys =
            listOf("auth.password.too_many_attempts", "account.contact.change_limit", "account.contact.admin_locked")
        keys.forEach { key ->
            val repository = FakeAccountRepository().apply { removeAnswers += refused(key) }
            val model = model(repository)

            model.remove("correct horse")
            advanceUntilIdle()

            assertEquals(confirming.copy(bannerKey = key), model.state.value, key)
        }
    }

    @Test
    fun `an empty password sends nothing, and the sheet never prints the contact`() = runTest(dispatcher) {
        val repository = FakeAccountRepository()
        val model = model(repository)

        model.remove("")
        advanceUntilIdle()

        assertEquals(emptyList(), repository.removals)
        assertFalse("rafi@example.com" in model.state.value.toString())
    }
}
