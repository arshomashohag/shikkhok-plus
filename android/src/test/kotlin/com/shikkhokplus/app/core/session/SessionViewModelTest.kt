package com.shikkhokplus.app.core.session

import com.shikkhokplus.app.core.network.LensEntryDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.profile.ProfileRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
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
 * The lens the app routes on, and what may change it.
 *
 * The mapper decides the SHAPE; this covers what only the ViewModel
 * can get wrong — honouring a lens nobody offered, and keeping a
 * stale list across a switch.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SessionViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class FakeProfile(
        private val answers: MutableList<AuthResult<MeDto>>,
    ) : ProfileRepository {
        var reads: Int = 0

        override suspend fun profile(): AuthResult<MeDto> {
            reads++
            return answers.removeFirstOrNull() ?: AuthResult.TransportFailure
        }

        override suspend fun save(selfName: String?, address: String?) =
            AuthResult.TransportFailure

        override suspend fun deleteAccount() = AuthResult.TransportFailure
    }

    private fun me(vararg lenses: Pair<String, Int>) =
        AuthResult.Ok(MeDto(lenses = lenses.map { LensEntryDto(it.first, it.second) }))

    @Test
    fun `it starts resolving, never assuming a lens`() {
        // **Resolving is not NoLens.** Treating "still asking" as
        // "nothing available" is the defect already fixed once at
        // sign-in, where a returning teacher saw a login screen.
        val model = SessionViewModel(FakeProfile(mutableListOf()))

        assertEquals(SessionUiState.Resolving, model.state.value)
    }

    @Test
    fun `resolving one lens routes straight through`() = runTest(dispatcher) {
        val model =
            SessionViewModel(FakeProfile(mutableListOf(me("teacher" to 2))))

        model.resolve()
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(SessionUiState.Ready(Lens.TEACHER), model.state.value)
    }

    @Test
    fun `choosing an offered lens takes it`() = runTest(dispatcher) {
        val model =
            SessionViewModel(
                FakeProfile(mutableListOf(me("teacher" to 2, "guardian" to 1))),
            )
        model.resolve()
        dispatcher.scheduler.advanceUntilIdle()

        model.choose(Lens.GUARDIAN)

        val ready = assertIs<SessionUiState.Ready>(model.state.value)
        assertEquals(Lens.GUARDIAN, ready.lens)
        assertEquals(true, ready.fromPicker)
    }

    @Test
    fun `choosing a lens that was NOT offered is ignored`() = runTest(dispatcher) {
        // **The one that matters.** The server refuses every endpoint
        // behind a lens it did not grant, so honouring this would turn
        // one wrong value into a wall of errors on every screen.
        val model =
            SessionViewModel(
                FakeProfile(mutableListOf(me("teacher" to 2, "guardian" to 1))),
            )
        model.resolve()
        dispatcher.scheduler.advanceUntilIdle()
        val before = model.state.value

        model.choose(Lens.STUDENT)

        assertEquals(before, model.state.value)
    }

    @Test
    fun `choosing before the list arrives is ignored`() = runTest(dispatcher) {
        val model = SessionViewModel(FakeProfile(mutableListOf(me("teacher" to 1))))

        model.choose(Lens.TEACHER)

        assertEquals(SessionUiState.Resolving, model.state.value)
    }

    @Test
    fun `switching re-reads rather than restoring the old list`() =
        runTest(dispatcher) {
            // A seat may have been accepted or removed since the first
            // read. Restoring the old list would offer a lens the
            // server no longer grants.
            val repository =
                FakeProfile(
                    mutableListOf(
                        me("teacher" to 2, "guardian" to 1),
                        me("teacher" to 2),
                    ),
                )
            val model = SessionViewModel(repository)
            model.resolve()
            dispatcher.scheduler.advanceUntilIdle()
            model.choose(Lens.GUARDIAN)

            model.switchLens()
            dispatcher.scheduler.advanceUntilIdle()

            assertEquals(2, repository.reads)
            // The guardian seat is gone, so the second read holds one
            // lens and routes straight through rather than offering it.
            assertEquals(SessionUiState.Ready(Lens.TEACHER), model.state.value)
        }

    @Test
    fun `a fresh resolve returns to Resolving before it answers`() =
        runTest(dispatcher) {
            // **What makes the sign-in path raceless.** The graph is
            // only composed once the session leaves `Resolving`, so
            // this is the state that holds the loader up while
            // `GET /v1/me` is in flight. A `resolve()` that left the
            // previous answer in place would let the graph compose
            // against a stale lens.
            val model =
                SessionViewModel(
                    FakeProfile(
                        mutableListOf(me("teacher" to 1), me("guardian" to 1)),
                    ),
                )
            model.resolve()
            dispatcher.scheduler.advanceUntilIdle()
            assertEquals(SessionUiState.Ready(Lens.TEACHER), model.state.value)

            model.resolve()

            assertEquals(SessionUiState.Resolving, model.state.value)
        }

    @Test
    fun `a switch leaves no lens in use while it re-resolves`() =
        runTest(dispatcher) {
            // **AC9.4.2, in the only place it can be enforced.** A
            // switch must not carry an open screen into the
            // destination lens's back stack -- an invitation resolves
            // the invitation lens [FR1.9d.1], which is scoped to a
            // seat, so landing Back inside another lens's history
            // would be a privacy failure wearing navigation clothes.
            //
            // Returning to `Resolving` is what guarantees it: the
            // whole graph leaves composition while no lens is in use,
            // so the destination lens builds a fresh stack rather
            // than inheriting one.
            val model =
                SessionViewModel(
                    FakeProfile(
                        mutableListOf(
                            me("teacher" to 1, "guardian" to 1),
                            me("teacher" to 1, "guardian" to 1),
                        ),
                    ),
                )
            model.resolve()
            dispatcher.scheduler.advanceUntilIdle()
            model.choose(Lens.TEACHER)

            model.switchLens()

            assertEquals(SessionUiState.Resolving, model.state.value)
        }

    @Test
    fun `a quiet refresh upgrades a lens-free session to its new lens`() =
        runTest(dispatcher) {
            // **The accept-your-first-seat case.** The server grants
            // the lens the moment a seat is accepted; without this
            // the person keeps the lens-free bar until they relaunch.
            val model =
                SessionViewModel(FakeProfile(mutableListOf(me(), me("student" to 1))))
            model.resolve()
            dispatcher.scheduler.advanceUntilIdle()
            assertEquals(SessionUiState.NoLens, model.state.value)

            model.refreshLenses()
            dispatcher.scheduler.advanceUntilIdle()

            assertEquals(SessionUiState.Ready(Lens.STUDENT), model.state.value)
        }

    @Test
    fun `a quiet refresh never publishes Resolving`() = runTest(dispatcher) {
        // **AC9.4.2.** Routing through `Resolving` takes the graph
        // out of composition, and tearing down an open invitation
        // list is what that rule forbids: Back would then land in the
        // newly granted lens's stack rather than on the list.
        val model =
            SessionViewModel(FakeProfile(mutableListOf(me(), me("student" to 1))))
        model.resolve()
        dispatcher.scheduler.advanceUntilIdle()

        val seen = mutableListOf<SessionUiState>()
        model.refreshLenses()
        seen += model.state.value
        dispatcher.scheduler.advanceUntilIdle()
        seen += model.state.value

        assertTrue(seen.none { it is SessionUiState.Resolving }, "$seen")
    }

    @Test
    fun `a quiet refresh does not interrupt with a picker`() = runTest(dispatcher) {
        // A person acting on a screen did not ask to change roles.
        // Two new lenses take the first and leave the switcher in
        // More, rather than throwing a picker over their work.
        val model =
            SessionViewModel(
                FakeProfile(
                    mutableListOf(me(), me("teacher" to 1, "guardian" to 1)),
                ),
            )
        model.resolve()
        dispatcher.scheduler.advanceUntilIdle()

        model.refreshLenses()
        dispatcher.scheduler.advanceUntilIdle()

        val ready = assertIs<SessionUiState.Ready>(model.state.value)
        assertEquals(Lens.TEACHER, ready.lens)
        // ...and the switcher becomes available, so the guardian side
        // is one tap away rather than lost.
        assertEquals(true, ready.fromPicker)
    }

    @Test
    fun `a quiet refresh leaves a lens already in use alone`() = runTest(dispatcher) {
        // Switching under someone mid-screen is never what they
        // asked for, even when a new lens genuinely appeared.
        val model =
            SessionViewModel(
                FakeProfile(
                    mutableListOf(
                        me("teacher" to 1),
                        me("teacher" to 1, "guardian" to 1),
                    ),
                ),
            )
        model.resolve()
        dispatcher.scheduler.advanceUntilIdle()

        model.refreshLenses()
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(SessionUiState.Ready(Lens.TEACHER), model.state.value)
    }

    @Test
    fun `a failed quiet refresh changes nothing`() = runTest(dispatcher) {
        // A dropped connection must not downgrade a working session
        // to NoLens and strip the bar.
        val model =
            SessionViewModel(
                FakeProfile(
                    mutableListOf(me("teacher" to 1), AuthResult.TransportFailure),
                ),
            )
        model.resolve()
        dispatcher.scheduler.advanceUntilIdle()

        model.refreshLenses()
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(SessionUiState.Ready(Lens.TEACHER), model.state.value)
    }

    @Test
    fun `a transport failure is reported, not silently treated as no lens`() =
        runTest(dispatcher) {
            val model =
                SessionViewModel(
                    FakeProfile(mutableListOf(AuthResult.TransportFailure)),
                )

            model.resolve()
            dispatcher.scheduler.advanceUntilIdle()

            assertIs<SessionUiState.Failed>(model.state.value)
        }
}
