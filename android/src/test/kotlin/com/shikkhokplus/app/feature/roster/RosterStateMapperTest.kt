package com.shikkhokplus.app.feature.roster

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RosterRowDto
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs

/**
 * The mapping decisions, which is where the screen's behaviour lives.
 *
 * Targeting the mapper rather than "the ViewModel" is what `team.md`
 * asks for: the decisions are here, and they are reachable without a
 * dispatcher.
 */
class RosterStateMapperTest {

    private fun row(
        status: String,
        fee: Money? = null,
    ): RosterRowDto =
        RosterRowDto(
            enrollmentId = "e-1",
            displayName = "Rahim",
            feeAmount = fee,
            status = status,
        )

    @Test
    fun `the status label comes from the server's enum, not from a date`() {
        // THE RULE [TC-9, D-31]. A client deciding "inactive" by comparing
        // inactiveFrom to today would be holding a business rule, and it
        // would look like presentation code.
        val state =
            RosterStateMapper.afterLoad("Physics", listOf(row("inactive")))

        val loaded = assertIs<RosterUiState.Loaded>(state)
        assertEquals("roster.status.inactive", loaded.rows.single().statusLabel)
    }

    @Test
    fun `each server status maps to its own key`() {
        val statuses = listOf("dormant", "active", "inactive")

        val labels =
            statuses.map { status ->
                val loaded =
                    assertIs<RosterUiState.Loaded>(
                        RosterStateMapper.afterLoad("Physics", listOf(row(status))),
                    )
                loaded.rows.single().statusLabel
            }

        assertEquals(
            listOf(
                "roster.status.dormant",
                "roster.status.active",
                "roster.status.inactive",
            ),
            labels,
        )
    }

    @Test
    fun `an unknown status fails loudly rather than defaulting`() {
        // A server that added a fourth status would otherwise render every
        // new seat under whichever label happened to be the fallback,
        // which is worse than showing nothing.
        val state = RosterStateMapper.afterLoad("Physics", listOf(row("archived")))

        val failed = assertIs<RosterUiState.Failed>(state)
        assertEquals(RosterStateMapper.UNEXPECTED_KEY, failed.messageKey)
    }

    @Test
    fun `an empty roster is Empty, not Loaded with no rows`() {
        val state = RosterStateMapper.afterLoad("Physics", emptyList())

        assertEquals(RosterUiState.Empty("Physics"), state)
    }

    @Test
    fun `retryable is read from the envelope, never inferred`() {
        val state =
            RosterStateMapper.afterError(
                ErrorEnvelope(
                    ErrorBody(
                        code = "ENROLLMENT_CLAIMED",
                        retryable = false,
                        messageKey = "enrollment.remove.claimed",
                    ),
                ),
            )

        val failed = assertIs<RosterUiState.Failed>(state)
        assertEquals("enrollment.remove.claimed", failed.messageKey)
        assertEquals(false, failed.retryable)
    }

    @Test
    fun `a money field decodes from a JSON string`() {
        val decoded =
            Json.decodeFromString<RosterRowDto>(
                """
                {"enrollment_id":"e-1","display_name":"Rahim",
                 "fee_amount":"1500.00","status":"active"}
                """.trimIndent(),
            )

        assertEquals(Money.of("1500.00"), decoded.feeAmount)
    }

    @Test
    fun `a money field sent as a JSON number fails loudly`() {
        // THE ACTUAL FAILURE MODE. A lenient decoder that quietly accepted
        // a number and converted would pass a happy-path test on both
        // sides while the value was already an IEEE 754 double [TC-7].
        assertFailsWith<Exception> {
            Json.decodeFromString<RosterRowDto>(
                """
                {"enrollment_id":"e-1","display_name":"Rahim",
                 "fee_amount":1500.00,"status":"active"}
                """.trimIndent(),
            )
        }
    }

    @Test
    fun `a batch's default fee decodes from a string and rejects a number`() {
        // The same obligation on the other money-carrying model class.
        val decoded =
            Json.decodeFromString<com.shikkhokplus.app.core.network.BatchDto>(
                """{"id":"b-1","name":"Physics","default_fee":"1500.00"}""",
            )
        assertEquals(Money.of("1500.00"), decoded.defaultFee)

        assertFailsWith<Exception> {
            Json.decodeFromString<com.shikkhokplus.app.core.network.BatchDto>(
                """{"id":"b-1","name":"Physics","default_fee":1500.00}""",
            )
        }
    }

    @Test
    fun `a null fee stays null and does not become zero`() {
        // Null means INHERIT the batch default; zero is a waiver. A
        // decoder that defaulted null to zero would silently charge
        // nothing [AC2.2.5].
        val decoded =
            Json.decodeFromString<RosterRowDto>(
                """{"enrollment_id":"e-1","display_name":"R","status":"active"}""",
            )

        assertEquals(null, decoded.feeAmount)
    }
}
