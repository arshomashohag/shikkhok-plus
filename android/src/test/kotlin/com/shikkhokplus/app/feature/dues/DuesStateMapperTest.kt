package com.shikkhokplus.app.feature.dues

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.DuesResponseDto
import com.shikkhokplus.app.core.network.DuesRowDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

/**
 * The dues mapper's state machine.
 *
 * **The mapping function is the unit under test, not "the ViewModel"**
 * [team.md]. It is pure, so every case here runs without a network, a
 * clock or a database.
 */
class DuesStateMapperTest {

    private fun row(
        name: String = "Rahim",
        batch: String = "Physics",
        outstanding: String = "1500.00",
        period: String? = "2027-01",
    ): DuesRowDto =
        DuesRowDto(
            enrollmentId = "seat-$name",
            batchId = "batch-1",
            batchName = batch,
            displayName = name,
            outstanding = Money.of(outstanding),
            oldestUnpaidPeriod = period,
        )

    @Test
    fun `rows map to the loaded state`() {
        val state = DuesStateMapper.afterLoad(DuesResponseDto(rows = listOf(row())))

        val loaded = assertIs<DuesUiState.Loaded>(state)
        assertEquals(1, loaded.rows.size)
        assertEquals("Rahim", loaded.rows[0].displayName)
        assertEquals("Physics", loaded.rows[0].batchName)
        assertEquals(Money.of("1500.00"), loaded.rows[0].outstanding)
        assertEquals("2027-01", loaded.rows[0].oldestUnpaidPeriod)
    }

    @Test
    fun `an empty list is its own state and not a loaded one with no rows`() {
        // An empty dues list is GOOD NEWS and deserves a sentence
        // saying so. A Loaded with no rows would render a blank, which
        // a teacher cannot tell apart from a failed load.
        assertEquals(
            DuesUiState.Empty,
            DuesStateMapper.afterLoad(DuesResponseDto(rows = emptyList())),
        )
    }

    @Test
    fun `the server's order is preserved and never re-sorted`() {
        // The server returned largest debt first. Re-sorting here --
        // even to the same order -- would be the client deciding a
        // domain list's order, which is one of the five erosion paths.
        val response =
            DuesResponseDto(
                rows =
                    listOf(
                        row(name = "Large", outstanding = "3000.00"),
                        row(name = "Small", outstanding = "100.00"),
                        row(name = "Mid", outstanding = "900.00"),
                    ),
            )

        val loaded = assertIs<DuesUiState.Loaded>(DuesStateMapper.afterLoad(response))

        assertEquals(
            listOf("Large", "Small", "Mid"),
            loaded.rows.map { it.displayName },
        )
    }

    @Test
    fun `a null oldest unpaid period stays null rather than becoming a blank`() {
        // There is no fallback figure. A period the server could not
        // name is not one this client may invent, and an empty string
        // would render as a stray label.
        val loaded =
            assertIs<DuesUiState.Loaded>(
                DuesStateMapper.afterLoad(DuesResponseDto(rows = listOf(row(period = null)))),
            )

        assertEquals(null, loaded.rows[0].oldestUnpaidPeriod)
    }

    @Test
    fun `a server error carries its message key and the server's retryable`() {
        // `retryable` is READ, never inferred from a status code: the
        // client holds no business logic, so it is told rather than
        // deciding.
        val envelope =
            ErrorEnvelope(
                ErrorBody(
                    code = "NO_TEACHER_LENS",
                    retryable = false,
                    messageKey = "authz.lens.not_available",
                ),
            )

        val failed = assertIs<DuesUiState.Failed>(DuesStateMapper.afterError(envelope))

        assertEquals("authz.lens.not_available", failed.messageKey)
        assertTrue(!failed.retryable)
    }

    @Test
    fun `a transport failure is always retryable`() {
        // There is no local write queue in V1, so the screen offers an
        // explicit retry rather than appearing to have succeeded.
        val failed =
            assertIs<DuesUiState.Failed>(DuesStateMapper.afterTransportFailure())

        assertEquals(DuesStateMapper.OFFLINE_KEY, failed.messageKey)
        assertTrue(failed.retryable)
    }
}
