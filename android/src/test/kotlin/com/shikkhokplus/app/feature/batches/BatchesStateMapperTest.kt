package com.shikkhokplus.app.feature.batches

import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * The batch list's mapping decisions, targeted directly.
 *
 * `BatchesStateMapper` moved out of `BatchesViewModel.kt` in D2 and
 * this file follows it, so the test target sits beside the thing it
 * tests the way `RosterStateMapperTest` already does. These need no
 * dispatcher and no fake repository: the mapper is pure, which is what
 * makes it the unit `team.md` asks for rather than "the ViewModel".
 */
class BatchesStateMapperTest {

    private fun batch(
        id: String = "b-1",
        name: String = "Physics",
        enrollmentCount: Int = 0,
        acceptedCount: Int = 0,
    ): BatchDto =
        BatchDto(
            id = id,
            name = name,
            enrollmentCount = enrollmentCount,
            acceptedCount = acceptedCount,
        )

    @Test
    fun `an empty list is Empty, not Loaded with no rows`() {
        // "No classes yet" and a blank list need different screens, and
        // a blank list explains neither.
        assertEquals(BatchesUiState.Empty, BatchesStateMapper.afterLoad(emptyList()))
    }

    @Test
    fun `both counts come from the response and neither is derived`() {
        // [BR1.2, BR1.3, NFR20.9]. **The discriminating arrangement**:
        // one row whose own numbers are 9 and 12. A mapper deriving
        // either from the list it holds would report 1 — the number of
        // rows — and look entirely reasonable doing it.
        val state =
            BatchesStateMapper.afterLoad(
                listOf(batch(enrollmentCount = 12, acceptedCount = 9)),
            )

        val row = assertIs<BatchesUiState.Loaded>(state).rows.single()
        assertEquals(9, row.acceptedCount)
        assertEquals(12, row.enrollmentCount)
    }

    @Test
    fun `the denominator keeps declined seats, so it never shrinks`() {
        // [BR1.4]. The server counts every seat the teacher created.
        // The client's job is to carry that number through unchanged:
        // "9 of 12" becoming "9 of 11" because somebody declined is the
        // failure, and it would be invisible — both numbers look
        // plausible.
        val state =
            BatchesStateMapper.afterLoad(
                listOf(batch(enrollmentCount = 12, acceptedCount = 9)),
            )

        val row = assertIs<BatchesUiState.Loaded>(state).rows.single()
        assertEquals(12, row.enrollmentCount)
    }

    @Test
    fun `a new batch carries zero of zero rather than nothing`() {
        // [W1]. The count renders from the first moment, so a teacher
        // sees the shape of the number before any seat exists rather
        // than meeting it later.
        val state = BatchesStateMapper.afterLoad(listOf(batch()))

        val row = assertIs<BatchesUiState.Loaded>(state).rows.single()
        assertEquals(0, row.acceptedCount)
        assertEquals(0, row.enrollmentCount)
    }

    @Test
    fun `counts stay with their own batch`() {
        // A mapper that zipped counts onto the wrong row would pass
        // every single-batch assertion above. Two batches with
        // deliberately different numbers is what catches it.
        val state =
            BatchesStateMapper.afterLoad(
                listOf(
                    batch(id = "b-1", name = "Physics", enrollmentCount = 12, acceptedCount = 9),
                    batch(id = "b-2", name = "Chemistry", enrollmentCount = 3, acceptedCount = 0),
                ),
            )

        val rows = assertIs<BatchesUiState.Loaded>(state).rows.associateBy { it.name }
        assertEquals(9, rows.getValue("Physics").acceptedCount)
        assertEquals(12, rows.getValue("Physics").enrollmentCount)
        assertEquals(0, rows.getValue("Chemistry").acceptedCount)
        assertEquals(3, rows.getValue("Chemistry").enrollmentCount)
    }

    @Test
    fun `retryable is read from the envelope, never inferred`() {
        val state =
            BatchesStateMapper.afterError(
                ErrorEnvelope(
                    ErrorBody(
                        code = "BATCH_NOT_FOUND",
                        retryable = false,
                        messageKey = "batch.not_found",
                    ),
                ),
            )

        val failed = assertIs<BatchesUiState.Failed>(state)
        assertEquals("batch.not_found", failed.messageKey)
        assertEquals(false, failed.retryable)
    }

    @Test
    fun `a transport failure is retryable and names the offline key`() {
        // There is no local write queue in V1, so the screen must offer
        // an explicit retry rather than appearing to have succeeded
        // [TC-8, D-9].
        val failed =
            assertIs<BatchesUiState.Failed>(BatchesStateMapper.afterTransportFailure())

        assertEquals(BatchesStateMapper.OFFLINE_KEY, failed.messageKey)
        assertEquals(true, failed.retryable)
    }
}
