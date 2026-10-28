package com.shikkhokplus.app.feature.student

import com.shikkhokplus.app.core.network.FamilyBatchViewDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import com.shikkhokplus.app.core.network.StudentBatchDto
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

/** S1 and S2's loading: what is read, and what one failure stops. */
@OptIn(ExperimentalCoroutinesApi::class)
class StudentBatchViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private class Fake(
        var batches: AuthResult<List<StudentBatchDto>> =
            AuthResult.Ok(listOf(StudentBatchDto("e-1", "Physics A"))),
        var view: AuthResult<FamilyBatchViewDto> =
            AuthResult.Ok(FamilyBatchViewDto(servedAt = "2026-10-28T09:00:00Z")),
    ) : StudentRepository {
        val reads = mutableListOf<String>()

        override suspend fun batches(): AuthResult<List<StudentBatchDto>> = batches.also { reads += "batches" }

        override suspend fun phone(): AuthResult<MeDto> =
            AuthResult.Ok(MeDto(phone = "+8801611477203")).also { reads += "phone" }

        override suspend fun batchView(enrollmentId: String): AuthResult<FamilyBatchViewDto> =
            view.also { reads += "view" }

        override suspend fun progress(enrollmentId: String): AuthResult<List<ProgressEntryDto>> =
            AuthResult.Ok<List<ProgressEntryDto>>(emptyList()).also { reads += "progress" }
    }

    @Test
    fun `a batch loads from the list, its view and the student's results`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentBatchViewModel(repository)

        model.load("e-1")
        advanceUntilIdle()

        assertIs<StudentBatchUiState.Loaded>(model.state.value)
        assertEquals(listOf("batches", "view", "progress"), repository.reads)
    }

    @Test
    fun `a seat not in the student's own list is not shown`() = runTest(dispatcher) {
        val repository = Fake()
        val model = StudentBatchViewModel(repository)

        model.load("someone-elses")
        advanceUntilIdle()

        assertIs<StudentBatchUiState.Failed>(model.state.value)
        assertEquals(listOf("batches"), repository.reads)
    }

    @Test
    fun `the first failed read stops the rest, and retry repeats it`() = runTest(dispatcher) {
        val repository = Fake(view = AuthResult.TransportFailure)
        val model = StudentBatchViewModel(repository)

        model.load("e-1")
        advanceUntilIdle()
        val failed = assertIs<StudentBatchUiState.Failed>(model.state.value)
        assertEquals(true, failed.retryable)
        assertEquals(listOf("batches", "view"), repository.reads)

        repository.view = AuthResult.Ok(FamilyBatchViewDto(servedAt = "2026-10-28T09:00:00Z"))
        model.retry()
        advanceUntilIdle()
        assertIs<StudentBatchUiState.Loaded>(model.state.value)
    }

    @Test
    fun `the account is read for the subtitle and for the empty state`() = runTest(dispatcher) {
        val repository = Fake(batches = AuthResult.Ok(emptyList()))
        val model = MyBatchesViewModel(repository)

        model.load()
        advanceUntilIdle()

        assertEquals(MyBatchesUiState.Empty("+8801611477203"), model.state.value)
        assertEquals(listOf("batches", "phone"), repository.reads)

        val withBatches = Fake()
        val loaded = MyBatchesViewModel(withBatches)
        loaded.load()
        advanceUntilIdle()
        assertEquals(listOf("batches", "phone"), withBatches.reads)
        assertEquals("+8801611477203", (loaded.state.value as MyBatchesUiState.Loaded).phone)
    }
}
