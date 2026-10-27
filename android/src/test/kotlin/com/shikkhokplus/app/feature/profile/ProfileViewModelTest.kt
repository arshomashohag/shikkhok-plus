package com.shikkhokplus.app.feature.profile

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MeDto
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
 * The profile ViewModel's own state machine.
 *
 * The screen, its state and the mapper all existed; nothing could
 * reach the server, and `GET /v1/me` carried no name or address to
 * reach. Both halves landed together.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ProfileViewModelTest {

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
        var result: AuthResult<MeDto> =
            AuthResult.Ok(MeDto(selfName = "Rahim", address = "Dhaka 1205")),
    ) : ProfileRepository {
        var reads = 0
        var saves = 0
        var sentName: String? = "unset"
        var sentAddress: String? = "unset"

        override suspend fun profile(): AuthResult<MeDto> {
            reads++
            return result
        }

        override suspend fun save(
            selfName: String?,
            address: String?,
        ): AuthResult<MeDto> {
            saves++
            sentName = selfName
            sentAddress = address
            return result
        }
    }

    @Test
    fun `it starts loading rather than empty`() {
        // An empty form would tell a person they have no profile when
        // nothing has been fetched yet.
        assertEquals(ProfileUiState.Loading, ProfileViewModel(FakeRepository()).state.value)
    }

    @Test
    fun `a loaded profile is shown`() = runTest(dispatcher) {
        val model = ProfileViewModel(FakeRepository())

        model.load()
        advanceUntilIdle()

        val state = assertIs<ProfileUiState.Viewing>(model.state.value)
        assertEquals("Rahim", state.selfName)
        assertEquals("Dhaka 1205", state.address)
    }

    @Test
    fun `a profile with no stored name is a real state, not a failure`() =
        runTest(dispatcher) {
            // A person whose teacher recorded only their number has no
            // profile row until they register. Showing the form empty
            // is the honest answer; an error would make an ordinary
            // first visit look broken.
            val model = ProfileViewModel(FakeRepository(result = AuthResult.Ok(MeDto())))

            model.load()
            advanceUntilIdle()

            val state = assertIs<ProfileUiState.Viewing>(model.state.value)
            assertEquals(null, state.selfName)
        }

    @Test
    fun `editing pre-fills from what is stored and calls nothing`() =
        runTest(dispatcher) {
            // A read here would discard anything typed if it landed
            // mid-edit.
            val repo = FakeRepository()
            val model = ProfileViewModel(repo)

            model.load()
            advanceUntilIdle()
            model.edit()

            val state = assertIs<ProfileUiState.Editing>(model.state.value)
            assertEquals("Rahim", state.selfName)
            assertEquals(1, repo.reads, "opening the form must not re-read")
        }

    @Test
    fun `a blank field is sent as null, never as an empty string`() =
        runTest(dispatcher) {
            // **Null means "leave it alone" to the server.** Sending
            // "" would erase stored data on a save the person thought
            // changed only the other field — and the screen has no
            // control that means "remove my address".
            val repo = FakeRepository()
            val model = ProfileViewModel(repo)

            model.save(selfName = "Rahim", address = "   ")
            advanceUntilIdle()

            assertEquals("Rahim", repo.sentName)
            assertEquals(null, repo.sentAddress, "a blank field must not clear stored data")
        }

    @Test
    fun `a successful save reports saved, not viewing`() = runTest(dispatcher) {
        // The screen says something after a save that it does not say
        // after a read.
        val model = ProfileViewModel(FakeRepository())

        model.save("Rahim", "Dhaka 1205")
        advanceUntilIdle()

        assertIs<ProfileUiState.Saved>(model.state.value)
    }

    @Test
    fun `a refusal carries the server's own message and retryability`() =
        runTest(dispatcher) {
            val repo =
                FakeRepository(
                    result =
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
            val model = ProfileViewModel(repo)

            model.load()
            advanceUntilIdle()

            val state = assertIs<ProfileUiState.Failed>(model.state.value)
            assertEquals("error.forbidden", state.messageKey)
            assertEquals(false, state.retryable)
        }

    @Test
    fun `a transport failure is retryable and retry repeats the save`() =
        runTest(dispatcher) {
            // Never automatic: V1 has no local queue, so a retry
            // nobody asked for would write without connectivity.
            val repo = FakeRepository(result = AuthResult.TransportFailure)
            val model = ProfileViewModel(repo)

            model.save("Rahim", "Dhaka")
            advanceUntilIdle()

            val state = assertIs<ProfileUiState.Failed>(model.state.value)
            assertEquals(true, state.retryable)
            assertEquals(1, repo.saves)

            model.retry()
            advanceUntilIdle()
            assertEquals(2, repo.saves, "retry must repeat the save, not a read")
        }
}
