package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.UsernameChangeDto
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
import kotlin.test.assertIs

/**
 * The Username screen's state machine (functional-spec 3.5) [FR7.1,
 * FR7.5]: loading the stored name, renaming, each refusal, the retry of
 * a failed write, and a password that reaches the server once and is
 * not kept.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class UsernameViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun modelOf(repository: FakeAccountRepository, onChanged: () -> Unit = {}) =
        UsernameViewModel(repository, repository, onChanged)

    @Test
    fun `the stored name is read and shown, and Change is always offered`() = runTest(dispatcher) {
        val repository = FakeAccountRepository().apply { profileAnswers += AuthResult.Ok(MeDto(username = "Nadia_K")) }
        val model = modelOf(repository)

        model.load()
        advanceUntilIdle()
        assertEquals(UsernameUiState.Viewing("Nadia_K"), model.state.value)

        model.startChange()
        assertEquals(UsernameUiState.Editing("Nadia_K"), model.state.value)
    }

    @Test
    fun `a rename is sent once with its password, and the profile is re-read`() = runTest(dispatcher) {
        var changed = 0
        val repository =
            FakeAccountRepository().apply {
                profileAnswers += AuthResult.Ok(MeDto(username = "nadia_k"))
                changeAnswers += AuthResult.Ok(UsernameChangeDto("Nadia.K", "2026-12-14T10:00:00Z"))
            }
        val model = modelOf(repository) { changed++ }
        model.load()
        advanceUntilIdle()
        model.startChange()

        model.save(" Nadia.K ", "correct horse")
        assertEquals(UsernameUiState.Editing("nadia_k", saving = true), model.state.value)
        model.save("Nadia.K", "correct horse")
        advanceUntilIdle()

        assertEquals(UsernameUiState.Changed("Nadia.K", "2026-12-14T10:00:00Z"), model.state.value)
        assertEquals(listOf<Pair<String, String?>>("Nadia.K" to "correct horse"), repository.changes)
        assertEquals(1, changed)
    }

    @Test
    fun `a lost connection offers a retry that resends the same request`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply {
                changeAnswers += AuthResult.TransportFailure
                changeAnswers += AuthResult.Ok(UsernameChangeDto("Nadia.K", null))
            }
        val model = modelOf(repository)
        model.startChange()

        model.save("Nadia.K", "correct horse")
        advanceUntilIdle()
        val failed = assertIs<UsernameUiState.Editing>(model.state.value)
        assertEquals(true, failed.retryable)

        model.save("Nadia.K", "correct horse")
        advanceUntilIdle()

        assertEquals(UsernameUiState.Changed("Nadia.K", null), model.state.value)
        assertEquals(2, repository.changes.size)
        assertEquals(repository.changes[0], repository.changes[1])
    }

    @Test
    fun `a refusal keeps the form, routed to its field`() = runTest(dispatcher) {
        val repository = FakeAccountRepository().apply { changeAnswers += refused("auth.password.current_wrong") }
        val model = modelOf(repository)
        model.startChange()

        model.save("Nadia.K", "wrong one")
        advanceUntilIdle()

        assertEquals(
            UsernameUiState.Editing(current = null, passwordKey = "auth.password.current_wrong"),
            model.state.value,
        )
    }

    @Test
    fun `nothing is sent without a name and a password`() = runTest(dispatcher) {
        val repository = FakeAccountRepository()
        val model = modelOf(repository)
        model.startChange()

        model.save("  ", "correct horse")
        model.save("Nadia.K", "")
        advanceUntilIdle()

        assertEquals(0, repository.changes.size)
    }

    @Test
    fun `cancel returns to the stored name, and editing clears a name refusal`() = runTest(dispatcher) {
        val repository = FakeAccountRepository().apply { changeAnswers += refused("account.username.unavailable") }
        val model = modelOf(repository)
        model.startChange()
        model.save("taken", "correct horse")
        advanceUntilIdle()

        model.edited("taken2")
        assertEquals(null, (model.state.value as UsernameUiState.Editing).usernameKey)

        model.cancel()
        assertEquals(UsernameUiState.Viewing(null), model.state.value)
    }

    @Test
    fun `a rename can start again after one, and the server decides`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply { changeAnswers += AuthResult.Ok(UsernameChangeDto("Nadia.K", null)) }
        val model = modelOf(repository)
        model.startChange()
        model.save("Nadia.K", "correct horse")
        advanceUntilIdle()

        model.startChange()

        assertEquals(UsernameUiState.Editing("Nadia.K"), model.state.value)
    }
}
