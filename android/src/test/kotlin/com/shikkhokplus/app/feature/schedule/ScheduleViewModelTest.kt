package com.shikkhokplus.app.feature.schedule

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.ScheduleSlotDto
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

@OptIn(ExperimentalCoroutinesApi::class)
class ScheduleViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private val slots = listOf(ScheduleSlotDto(0, "16:00", "17:00"))

    private class Fake(
        var saveResult: AuthResult<List<ScheduleSlotDto>>,
    ) : ScheduleRepository {
        var saves = 0

        override suspend fun schedule(batchId: String) = AuthResult.Ok(emptyList<ScheduleSlotDto>())

        override suspend fun save(batchId: String, slots: List<ScheduleSlotDto>): AuthResult<List<ScheduleSlotDto>> {
            saves++
            return saveResult
        }
    }

    @Test
    fun `a saved schedule reports Saved and holds what was stored`() = runTest(dispatcher) {
        val model = ScheduleViewModel(Fake(AuthResult.Ok(slots)))

        model.save("b-1", slots)
        advanceUntilIdle()

        assertEquals(WriteState.Saved, model.writeState.value)
        assertEquals(slots, model.slots.value)
    }

    @Test
    fun `a refused schedule reaches the screen`() = runTest(dispatcher) {
        val refusal = ErrorEnvelope(ErrorBody("SCHEDULE_DUPLICATE_SLOT", false, "schedule.duplicate_slot"))
        val model = ScheduleViewModel(Fake(AuthResult.Refused(refusal)))

        model.save("b-1", slots)
        advanceUntilIdle()

        assertEquals("schedule.duplicate_slot", assertIs<WriteState.Failed>(model.writeState.value).messageKey)
    }

    @Test
    fun `a second tap while saving does not save twice`() = runTest(dispatcher) {
        val repository = Fake(AuthResult.Ok(slots))
        val model = ScheduleViewModel(repository)

        model.save("b-1", slots)
        model.save("b-1", slots)
        advanceUntilIdle()

        assertEquals(1, repository.saves)
    }

    @Test
    fun `the stored schedule loads`() = runTest(dispatcher) {
        val model = ScheduleViewModel(Fake(AuthResult.Ok(slots)))
        assertEquals(null, model.slots.value, "null while loading")

        model.load("b-1")
        advanceUntilIdle()

        assertEquals(emptyList(), model.slots.value)
    }
}
