package com.shikkhokplus.app.feature.batches

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.ui.WriteState
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
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The batch list's state machine and its mapping decisions.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class BatchesViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake(
        var result: AuthResult<List<BatchDto>> = AuthResult.Ok(emptyList()),
    ) : BatchesRepository {
        var calls = 0

        override suspend fun batches(): AuthResult<List<BatchDto>> {
            calls += 1
            return result
        }

        var created: Triple<String, List<String>, String?>? = null
        var createResult: AuthResult<BatchDto> =
            AuthResult.Ok(
                BatchDto(id = "b-new", name = "new", subjects = emptyList()),
            )

        override suspend fun createBatch(
            name: String,
            subjects: List<String>,
            defaultFee: String?,
            feeDueDay: Int?,
            schedule: List<com.shikkhokplus.app.core.network.ScheduleSlotDto>,
        ): AuthResult<BatchDto> {
            created = Triple(name, subjects, defaultFee)
            return createResult
        }
    }

    private fun dto(name: String, count: Int = 0) =
        BatchDto(
            id = "b-$name",
            name = name,
            subjects = listOf("Physics"),
            defaultFee = Money.of("1500.00"),
            feeDueDay = 10,
            active = true,
            enrollmentCount = count,
        )

    @Test
    fun `starts idle`() {
        assertEquals(BatchesUiState.Idle, BatchesViewModel(Fake()).state.value)
    }

    @Test
    fun `shows loading while in flight`() = runTest(dispatcher) {
        val model = BatchesViewModel(Fake())

        model.load()

        assertEquals(BatchesUiState.Loading, model.state.value)
    }

    @Test
    fun `an empty list is Empty, not Loaded with no rows`() = runTest(dispatcher) {
        // "No classes yet" and a blank list need different screens, and
        // a blank list explains neither.
        val model = BatchesViewModel(Fake())

        model.load()
        advanceUntilIdle()

        assertEquals(BatchesUiState.Empty, model.state.value)
    }

    @Test
    fun `a loaded list carries the SERVER's count`() = runTest(dispatcher) {
        // Counted server-side [TC-9]. A client counting a roster it has
        // not fetched would be guessing; one that fetched every roster
        // to count would be the N+1 shape moved to the client.
        val model = BatchesViewModel(Fake(AuthResult.Ok(listOf(dto("Physics", 12)))))

        model.load()
        advanceUntilIdle()

        val state = assertIs<BatchesUiState.Loaded>(model.state.value)
        assertEquals(12, state.rows.single().enrollmentCount)
    }

    @Test
    fun `the fee stays a Money all the way to the renderer`() = runTest(dispatcher) {
        // Formatting here would put the rendering decision on the
        // client, and the Bangla rendering is server-side [OQ-B1-1].
        val model = BatchesViewModel(Fake(AuthResult.Ok(listOf(dto("Physics")))))

        model.load()
        advanceUntilIdle()

        val state = assertIs<BatchesUiState.Loaded>(model.state.value)
        assertEquals(Money.of("1500.00"), state.rows.single().defaultFee)
    }

    @Test
    fun `a refusal reads retryable from the envelope`() = runTest(dispatcher) {
        val model =
            BatchesViewModel(
                Fake(
                    AuthResult.Refused(
                        ErrorEnvelope(
                            ErrorBody(
                                code = "NO_TEACHER_LENS",
                                retryable = false,
                                messageKey = "authz.lens.not_available",
                            ),
                        ),
                    ),
                ),
            )

        model.load()
        advanceUntilIdle()

        val state = assertIs<BatchesUiState.Failed>(model.state.value)
        assertEquals("authz.lens.not_available", state.messageKey)
        assertEquals(false, state.retryable)
    }

    @Test
    fun `a transport failure is retryable`() = runTest(dispatcher) {
        val model = BatchesViewModel(Fake(AuthResult.TransportFailure))

        model.load()
        advanceUntilIdle()

        val state = assertIs<BatchesUiState.Failed>(model.state.value)
        assertTrue(state.retryable)
    }

    @Test
    fun `a successful create reloads the list rather than inserting locally`() =
        runTest(dispatcher) {
            // NO optimistic insert. V1 accepts no write without
            // connectivity [TC-8, D-9], so a row added locally before
            // the server confirmed would be a local write queue -- which
            // this product deliberately does not have.
            val repository = Fake()
            val model = BatchesViewModel(repository)

            model.create("Class 9", listOf("Physics"), "1500.00", 10)
            advanceUntilIdle()

            assertEquals(1, repository.calls, "the list must reload from the server")
            assertEquals("1500.00", repository.created?.third)
        }

    private fun refusal() =
        AuthResult.Refused(
            ErrorEnvelope(
                ErrorBody(
                    code = "BATCH_NEEDS_A_SUBJECT",
                    retryable = false,
                    messageKey = "batch.create.subject_required",
                ),
            ),
        )

    @Test
    fun `a refused create reaches the form and does not reload`() = runTest(dispatcher) {
        // **Rewritten, not loosened.** This used to assert the refusal
        // on the LIST's state, which is exactly where a concurrent
        // reload could overwrite it. It now belongs to the form that
        // caused it, which stays open to show it.
        val repository = Fake()
        repository.createResult = refusal()
        val model = BatchesViewModel(repository)

        model.create("Class 9", emptyList(), null, null)
        advanceUntilIdle()

        val write = assertIs<WriteState.Failed>(model.writeState.value)
        assertEquals("batch.create.subject_required", write.messageKey)
        assertEquals(0, repository.calls, "a failed create must not reload")
    }

    @Test
    fun `a refused create is not hidden by a list reload racing it`() =
        runTest(dispatcher) {
            // **The reported bug, reproduced.** Returning to the list
            // re-runs its load, so a refused create and a list read
            // were in flight together and the last answer won. A
            // teacher saw their old list, no error, and no class.
            val repository = Fake(AuthResult.Ok(emptyList()))
            repository.createResult = refusal()
            val model = BatchesViewModel(repository)

            model.create("Class 9", listOf("Physics"), "1500", 10)
            model.load()
            advanceUntilIdle()

            assertIs<WriteState.Failed>(model.writeState.value)
        }

    @Test
    fun `a successful create reports Saved so the form can close`() =
        runTest(dispatcher) {
            val model = BatchesViewModel(Fake())

            model.create("Class 9", listOf("Physics"), null, null)
            advanceUntilIdle()

            assertEquals(WriteState.Saved, model.writeState.value)
        }

    @Test
    fun `a second tap while saving does not create twice`() = runTest(dispatcher) {
        // On a slow network the button is the only thing a person can
        // press. Two taps must not be two classes.
        var creates = 0
        val repository =
            object : BatchesRepository {
                override suspend fun batches() = AuthResult.Ok(emptyList<BatchDto>())

                override suspend fun createBatch(
                    name: String,
                    subjects: List<String>,
                    defaultFee: String?,
                    feeDueDay: Int?,
                    schedule: List<com.shikkhokplus.app.core.network.ScheduleSlotDto>,
                ): AuthResult<BatchDto> {
                    creates += 1
                    return AuthResult.Ok(BatchDto(id = "b", name = name))
                }
            }
        val model = BatchesViewModel(repository)

        model.create("Class 9", listOf("Physics"), null, null)
        model.create("Class 9", listOf("Physics"), null, null)
        advanceUntilIdle()

        assertEquals(1, creates)
    }

    @Test
    fun `acknowledging a write lets the next form open clean`() = runTest(dispatcher) {
        val repository = Fake()
        repository.createResult = refusal()
        val model = BatchesViewModel(repository)
        model.create("Class 9", listOf("Physics"), null, null)
        advanceUntilIdle()

        model.acknowledgeWrite()

        assertEquals(WriteState.Idle, model.writeState.value)
        assertNull((model.writeState.value as? WriteState.Failed)?.messageKey)
    }

    @Test
    fun `retry runs only when asked`() = runTest(dispatcher) {
        // No silent retry [TC-8, D-9]: one request, and the user decides.
        val repository = Fake(AuthResult.TransportFailure)
        val model = BatchesViewModel(repository)

        model.load()
        advanceUntilIdle()
        assertEquals(1, repository.calls)

        model.retry()
        advanceUntilIdle()
        assertEquals(2, repository.calls)
    }
}
