package com.shikkhokplus.app.feature.fees

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ClaimDto
import com.shikkhokplus.app.core.network.FeeCycleDto
import com.shikkhokplus.app.core.network.PaymentDestinationDto
import com.shikkhokplus.app.core.network.RosterFeeRowDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The mapping decisions, which is where the fee screens' behaviour lives.
 *
 * Targeting the mapper rather than "the ViewModel" is what `team.md`
 * asks for: the decisions are here and they are reachable without a
 * dispatcher.
 *
 * **The case this file exists for is the waived cycle.** Its balance is
 * zero and nobody paid, so a client-side `if (balance > 0)` reports it
 * as "Paid" — the exact business-rule-in-presentation's-clothes the
 * team practice names for this surface.
 */
class FeeStateMapperTest {

    private fun cycle(
        status: String,
        period: String = "2027-02",
        charged: String = "1000.00",
        outstanding: String = "1000.00",
    ): FeeCycleDto =
        FeeCycleDto(
            period = period,
            dueDate = "2027-02-28",
            charged = Money.of(charged),
            outstanding = Money.of(outstanding),
            status = status,
        )

    private fun claim(
        status: String,
        approved: String? = null,
        disposition: String? = null,
        previous: Map<String, String?>? = null,
    ): ClaimDto =
        ClaimDto(
            claimId = "c-1",
            period = "2027-02",
            claimedAmount = Money.of("1500.00"),
            approvedAmount = approved?.let { Money.of(it) },
            status = status,
            shortfallDisposition = disposition,
            channel = "bKash",
            submittedAt = "2027-02-10T10:00:00Z",
            previousDecision = previous,
        )

    // -----------------------------------------------------------------
    // The status enum, and the case that needs four values.
    // -----------------------------------------------------------------

    @Test
    fun `the status label comes from the server's enum, never from an amount`() {
        val state = FeeStateMapper.afterLoad(listOf(cycle("unpaid")), Money.of("1000.00"))

        val loaded = assertIs<FeeUiState.Loaded>(state)
        assertEquals("fees.status.unpaid", loaded.rows.single().statusLabel)
    }

    @Test
    fun `each server status maps to its own key`() {
        val expected =
            mapOf(
                "paid" to "fees.status.paid",
                "partly_paid" to "fees.status.partly_paid",
                "unpaid" to "fees.status.unpaid",
                "waived" to "fees.status.waived",
            )

        expected.forEach { (status, key) ->
            val row = FeeStateMapper.toRow(cycle(status))
            assertNotNull(row, "status '$status' did not map")
            assertEquals(key, row.statusLabel)
        }
    }

    @Test
    fun `a waived cycle is settled but is not the paid label`() {
        // THE CASE THE ENUM EXISTS FOR. Both have a zero balance, so a
        // two-value client-side test cannot tell them apart -- and
        // calling a waiver "Paid" tells the student somebody paid.
        val waived = FeeStateMapper.toRow(cycle("waived", outstanding = "0.00"))
        val paid = FeeStateMapper.toRow(cycle("paid", outstanding = "0.00"))

        assertNotNull(waived)
        assertNotNull(paid)
        assertTrue(waived.isSettled)
        assertTrue(paid.isSettled)
        assertEquals("fees.status.waived", waived.statusLabel)
        assertEquals("fees.status.paid", paid.statusLabel)
    }

    @Test
    fun `isSettled follows the status and not the outstanding amount`() {
        // A server that reported zero outstanding on an UNPAID cycle
        // would be inconsistent, and the mapper must follow the enum
        // rather than silently re-deciding from the figure. If the two
        // ever disagree the enum wins, because the enum is the rule.
        val row = FeeStateMapper.toRow(cycle("unpaid", outstanding = "0.00"))

        assertNotNull(row)
        assertEquals(false, row.isSettled)
    }

    @Test
    fun `an unknown status fails rather than defaulting`() {
        // A fifth status rendering under whichever label happened to be
        // the fallback is worse than showing nothing: it looks correct.
        assertNull(FeeStateMapper.toRow(cycle("deferred")))

        val state = FeeStateMapper.afterLoad(listOf(cycle("deferred")), Money.ZERO)
        val failed = assertIs<FeeUiState.Failed>(state)
        assertEquals(FeeStateMapper.UNEXPECTED_KEY, failed.messageKey)
        assertEquals(false, failed.retryable)
    }

    // -----------------------------------------------------------------
    // The total, and what the client must not compute.
    // -----------------------------------------------------------------

    @Test
    fun `the total is carried through and never summed here`() {
        // The temptation is `rows.sumOf { it.outstanding }`, which is
        // the client doing money arithmetic -- forbidden outright
        // [TC-9, D-31] -- and wrong the moment the history paginates.
        // The server's figure is used even when it differs from the
        // visible rows, which is exactly what makes this assertable.
        val state =
            FeeStateMapper.afterLoad(
                listOf(cycle("unpaid", outstanding = "1000.00")),
                Money.of("4500.00"),
            )

        val loaded = assertIs<FeeUiState.Loaded>(state)
        assertEquals(Money.of("4500.00"), loaded.totalOutstanding)
    }

    @Test
    fun `no periods at all is Empty rather than an empty list`() {
        // Nothing CHARGED is not the same as everything paid, and the
        // copy differs.
        assertIs<FeeUiState.Empty>(
            FeeStateMapper.afterLoad(emptyList(), Money.ZERO),
        )
    }

    @Test
    fun `periods are ordered newest first`() {
        val state =
            FeeStateMapper.afterLoad(
                listOf(
                    cycle("unpaid", period = "2027-01"),
                    cycle("unpaid", period = "2027-03"),
                    cycle("unpaid", period = "2027-02"),
                ),
                Money.of("3000.00"),
            )

        val loaded = assertIs<FeeUiState.Loaded>(state)
        assertEquals(
            listOf("2027-03", "2027-02", "2027-01"),
            loaded.rows.map { it.period },
        )
    }

    // -----------------------------------------------------------------
    // The roster row.
    // -----------------------------------------------------------------

    @Test
    fun `a roster row with no generated period carries no status`() {
        val row =
            FeeStateMapper.toRosterRow(
                RosterFeeRowDto(
                    enrollmentId = "e-1",
                    displayName = "Rahim",
                    outstanding = Money.ZERO,
                ),
            )

        assertNotNull(row)
        assertNull(row.statusLabel)
        assertEquals(false, row.owesSomething)
    }

    @Test
    fun `a roster row owing money says so as a field`() {
        // The field exists so no composable writes
        // `if (row.outstanding > Money.ZERO)`.
        val row =
            FeeStateMapper.toRosterRow(
                RosterFeeRowDto(
                    enrollmentId = "e-1",
                    displayName = "Rahim",
                    outstanding = Money.of("1500.00"),
                    currentPeriod = "2027-02",
                    currentStatus = "unpaid",
                ),
            )

        assertNotNull(row)
        assertTrue(row.owesSomething)
        assertEquals("fees.status.unpaid", row.statusLabel)
    }

    @Test
    fun `an unknown roster status fails rather than defaulting`() {
        assertNull(
            FeeStateMapper.toRosterRow(
                RosterFeeRowDto(
                    enrollmentId = "e-1",
                    displayName = "Rahim",
                    outstanding = Money.ZERO,
                    currentStatus = "deferred",
                ),
            ),
        )
    }

    // -----------------------------------------------------------------
    // Claims, and the two things the submitter must be shown.
    // -----------------------------------------------------------------

    @Test
    fun `each claim status maps to its own key`() {
        val expected =
            mapOf(
                "pending" to "fees.claim.pending",
                "approved_full" to "fees.claim.approved_full",
                "approved_partial" to "fees.claim.approved_partial",
                "rejected" to "fees.claim.rejected",
            )

        expected.forEach { (status, key) ->
            val row = FeeStateMapper.toClaimRow(claim(status))
            assertNotNull(row, "claim status '$status' did not map")
            assertEquals(key, row.statusLabel)
        }
    }

    @Test
    fun `a rejection is decided even though it has no approved amount`() {
        // THE SEPARATING CASE for `isDecided`. A composable testing
        // `approvedAmount != null` would render a rejection as still
        // pending -- so the submitter would never learn it was
        // refused, which is the failure BR5.6 names.
        val row = FeeStateMapper.toClaimRow(claim("rejected"))

        assertNotNull(row)
        assertTrue(row.isDecided)
        assertNull(row.approvedAmount)
        assertEquals("fees.claim.rejected", row.statusLabel)
    }

    @Test
    fun `a pending claim is not decided`() {
        val row = FeeStateMapper.toClaimRow(claim("pending"))

        assertNotNull(row)
        assertEquals(false, row.isDecided)
    }

    @Test
    fun `a partial approval carries its disposition`() {
        // The two dispositions have OPPOSITE consequences for the
        // student, so the value is shown rather than summarised.
        val carried =
            FeeStateMapper.toClaimRow(
                claim("approved_partial", approved = "600.00", disposition = "carried"),
            )
        val waived =
            FeeStateMapper.toClaimRow(
                claim("approved_partial", approved = "600.00", disposition = "waived"),
            )

        assertNotNull(carried)
        assertNotNull(waived)
        assertEquals("fees.disposition.carried", carried.dispositionLabel)
        assertEquals("fees.disposition.waived", waived.dispositionLabel)
    }

    @Test
    fun `a correction is surfaced to the submitter`() {
        // [BR5.7, FR9.2] A correction hidden from the person whose
        // money it concerns is the exact asymmetry FR9.2 forbids, and
        // this field is what puts it on their screen.
        val row =
            FeeStateMapper.toClaimRow(
                claim(
                    "approved_partial",
                    approved = "600.00",
                    disposition = "waived",
                    previous = mapOf("status" to "approved_full", "approved_amount" to "1000.00"),
                ),
            )

        assertNotNull(row)
        assertEquals(FeeStateMapper.CORRECTION_KEY, row.correctionNoticeKey)
    }

    @Test
    fun `an uncorrected claim carries no correction notice`() {
        val row = FeeStateMapper.toClaimRow(claim("approved_full", approved = "1500.00"))

        assertNotNull(row)
        assertNull(row.correctionNoticeKey)
    }

    @Test
    fun `an unknown disposition fails rather than defaulting`() {
        // Defaulting here would tell a student their shortfall was
        // waived when it was carried, or the reverse.
        assertNull(
            FeeStateMapper.toClaimRow(
                claim("approved_partial", approved = "600.00", disposition = "deferred"),
            ),
        )
    }

    // -----------------------------------------------------------------
    // The payment destination.
    // -----------------------------------------------------------------

    @Test
    fun `an unset destination is Unset rather than a known one with blanks`() {
        // [NFR14.34] A null field invites a client placeholder; an
        // absent object leaves nothing to render and the copy tells
        // the person to ask the teacher.
        val destination = FeeStateMapper.toDestination(null)

        assertIs<PaymentDestination.Unset>(destination)
    }

    @Test
    fun `a known destination carries the server's channel list`() {
        // [BR6.5] A list rendered as labels, never a sealed type with
        // a branch per channel: adding one server-side would then need
        // an app release, and an installed app cannot be forced to
        // update.
        val destination =
            FeeStateMapper.toDestination(
                PaymentDestinationDto(
                    collectionNumber = "01711000000",
                    collectionChannel = "bKash",
                    channels = listOf("bKash", "Nagad", "Rocket", "cash"),
                ),
            )

        val known = assertIs<PaymentDestination.Known>(destination)
        assertEquals("01711000000", known.collectionNumber)
        assertEquals(listOf("bKash", "Nagad", "Rocket", "cash"), known.channels)
    }

    @Test
    fun `no channel name is hardcoded in the mapper`() {
        // The channel set is DATA. A mapper that knew the four names
        // would be the client list BR6.5 forbids, one indirection
        // further back.
        val destination =
            FeeStateMapper.toDestination(
                PaymentDestinationDto(
                    collectionNumber = "01711000000",
                    channels = listOf("Upay", "SureCash"),
                ),
            )

        val known = assertIs<PaymentDestination.Known>(destination)
        assertEquals(listOf("Upay", "SureCash"), known.channels)
    }

    // -----------------------------------------------------------------
    // Failure states.
    // -----------------------------------------------------------------

    @Test
    fun `an unreachable server is retryable`() {
        val failed = assertIs<FeeUiState.Failed>(FeeStateMapper.offline())

        assertEquals(FeeStateMapper.OFFLINE_KEY, failed.messageKey)
        assertTrue(failed.retryable)
    }

    @Test
    fun `retryability is taken from the server and never inferred`() {
        // The client holds no business logic [TC-9]: it is TOLD
        // whether retrying could help rather than guessing from a
        // status code.
        val failed =
            assertIs<FeeUiState.Failed>(
                FeeStateMapper.failed("fees.claim.no_open_cycle", retryable = false),
            )

        assertEquals("fees.claim.no_open_cycle", failed.messageKey)
        assertEquals(false, failed.retryable)
    }
}
