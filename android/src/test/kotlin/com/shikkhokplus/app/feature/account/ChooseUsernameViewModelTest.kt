package com.shikkhokplus.app.feature.account

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

/**
 * The choose-username gate's state machine (functional-spec 3.4) [FR5.2,
 * FR5.4]: saving, done, each refusal, the re-read when another device
 * chose first, and the explicit retry of a failed write [TC-8, D-9].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ChooseUsernameViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val chosen = AuthResult.Ok(UsernameChangeDto("Nadia_K", null))

    private class Session {
        var chosenCalls = 0
        val rereadAnswers = ArrayDeque<Boolean>()
        var rereads = 0

        fun chosen() {
            chosenCalls++
        }

        suspend fun reread(): Boolean {
            rereads++
            return rereadAnswers.removeFirstOrNull() ?: false
        }
    }

    private fun model(repository: FakeAccountRepository, session: Session) =
        ChooseUsernameViewModel(repository, session::chosen, session::reread)

    @Test
    fun `a 200 is Done and lifts the gate, with no password sent`() = runTest(dispatcher) {
        val repository = FakeAccountRepository().apply { changeAnswers += chosen }
        val session = Session()
        val model = model(repository, session)

        model.submit("  nadia_k ")
        assertEquals(ChooseUsernameUiState.Editing(saving = true), model.state.value)
        advanceUntilIdle()

        assertEquals(ChooseUsernameUiState.Done, model.state.value)
        assertEquals(1, session.chosenCalls)
        assertEquals(listOf<Pair<String, String?>>("nadia_k" to null), repository.changes)
    }

    @Test
    fun `a format or unavailable refusal stays on the form with its key`() = runTest(dispatcher) {
        listOf("account.username.bad_dot", "account.username.unavailable").forEach { key ->
            val repository = FakeAccountRepository().apply { changeAnswers += refused(key) }
            val session = Session()
            val model = model(repository, session)

            model.submit("nadia..k")
            advanceUntilIdle()

            assertEquals(ChooseUsernameUiState.Editing(messageKey = key), model.state.value)
            assertEquals(0, session.chosenCalls)
        }
    }

    @Test
    fun `another device chose first, the account is re-read and the gate is done`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply { changeAnswers += refused("account.username.password_required") }
        val session = Session().apply { rereadAnswers += true }
        val model = model(repository, session)

        model.submit("nadia_k")
        advanceUntilIdle()

        assertEquals(ChooseUsernameUiState.Done, model.state.value)
        assertEquals(1, session.rereads)
    }

    @Test
    fun `a failed re-read is retryable, and the retry reads again`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply { changeAnswers += refused("account.username.password_required") }
        val session = Session().apply { rereadAnswers += false }
        val model = model(repository, session)
        model.submit("nadia_k")
        advanceUntilIdle()
        assertEquals(
            ChooseUsernameUiState.Editing(messageKey = ChooseUsernameStateMapper.OFFLINE_KEY, retryable = true),
            model.state.value,
        )

        session.rereadAnswers += true
        model.retry()
        advanceUntilIdle()

        assertEquals(ChooseUsernameUiState.Done, model.state.value)
        assertEquals(2, session.rereads)
        assertEquals(1, repository.changes.size, "the choice is not sent again")
    }

    @Test
    fun `a 503 or no answer offers a retry that resends the same name`() = runTest(dispatcher) {
        val repository =
            FakeAccountRepository().apply {
                changeAnswers += refused("error.temporarily_unavailable", retryable = true)
                changeAnswers += AuthResult.TransportFailure
                changeAnswers += chosen
            }
        val model = model(repository, Session())

        model.submit("nadia_k")
        advanceUntilIdle()
        assertEquals(
            ChooseUsernameUiState.Editing(messageKey = "error.temporarily_unavailable", retryable = true),
            model.state.value,
        )
        model.retry()
        advanceUntilIdle()
        model.retry()
        advanceUntilIdle()

        assertEquals(ChooseUsernameUiState.Done, model.state.value)
        assertEquals(listOf("nadia_k", "nadia_k", "nadia_k"), repository.changes.map { it.first })
    }

    @Test
    fun `a lookup ceiling is said and not retried by itself`() = runTest(dispatcher) {
        val repository = FakeAccountRepository().apply { changeAnswers += refused("auth.lookup.too_many") }
        val model = model(repository, Session())

        model.submit("nadia_k")
        advanceUntilIdle()
        model.retry()
        advanceUntilIdle()

        assertEquals(ChooseUsernameUiState.Editing(messageKey = "auth.lookup.too_many"), model.state.value)
        assertEquals(1, repository.changes.size)
    }

    @Test
    fun `a double Continue sends one choice, and a blank one sends none`() = runTest(dispatcher) {
        val repository = FakeAccountRepository().apply { changeAnswers += chosen }
        val model = model(repository, Session())

        model.submit("   ")
        model.submit("nadia_k")
        model.submit("nadia_k")
        advanceUntilIdle()

        assertEquals(1, repository.changes.size)
    }

    @Test
    fun `the gate checks names on the authenticated lookup`() = runTest(dispatcher) {
        val repository = FakeAccountRepository()
        val model = model(repository, Session())

        model.edited("nadia_k")
        advanceUntilIdle()

        assertEquals(listOf("nadia_k"), repository.lookups)
    }
}
