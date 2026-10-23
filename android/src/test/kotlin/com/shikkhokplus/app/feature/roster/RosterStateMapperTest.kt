package com.shikkhokplus.app.feature.roster

import com.shikkhokplus.app.core.model.LinkState
import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RosterRowDto
import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertNull

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
        studentState: String = "pending",
        guardianState: String = "absent",
        isRemovable: Boolean = true,
        guardianPhone: String? = null,
        enrollmentId: String = "e-1",
        displayName: String = "Rahim",
    ): RosterRowDto =
        RosterRowDto(
            enrollmentId = enrollmentId,
            displayName = displayName,
            guardianPhone = guardianPhone,
            feeAmount = fee,
            status = status,
            studentState = studentState,
            guardianState = guardianState,
            isRemovable = isRemovable,
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
                 "fee_amount":"1500.00","status":"active",
                 "student_state":"pending","guardian_state":"absent",
                 "is_removable":true}
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
                 "fee_amount":1500.00,"status":"active",
                 "student_state":"pending","guardian_state":"absent",
                 "is_removable":true}
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
                """
                {"enrollment_id":"e-1","display_name":"R","status":"active",
                 "student_state":"pending","guardian_state":"absent",
                 "is_removable":true}
                """.trimIndent(),
            )

        assertEquals(null, decoded.feeAmount)
    }

    // ---------------------------------------------------------------
    // D2: the decisions the row carries so the screen does not make
    // them. Each of these is a field precisely BECAUSE a composable
    // computing it would be comparing a domain value to choose a
    // control -- the slip D1 made on `InvitationCard` and corrected.
    // ---------------------------------------------------------------

    @Test
    fun `isDeclined is set for a declined link and not for a pending one`() {
        // [BR1.1, AC1.3.3a]. Declined is marked because it is abnormal
        // and usually a mistyped number. Pending is NOT, because it is
        // the normal state of a new seat: marking most rows would flag
        // normality as a problem, which is the clutter the superseded
        // AC1.3.3 refused the roster for in the first place.
        val declined =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    "Physics",
                    listOf(row("dormant", studentState = "declined")),
                ),
            )
        val pending =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    "Physics",
                    listOf(row("dormant", studentState = "pending")),
                ),
            )

        assertEquals(true, declined.rows.single().isDeclined)
        assertEquals(false, pending.rows.single().isDeclined)
    }

    @Test
    fun `a guardian decline marks the row too`() {
        // Either link's refusal is a refusal somebody made, and the
        // teacher's remedy is the same: check the number they typed.
        // A mark keyed only on the student link would leave the
        // commonest mistyped-guardian-number case unmarked.
        val loaded =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    "Physics",
                    listOf(
                        row(
                            "active",
                            studentState = "accepted",
                            guardianState = "declined",
                        ),
                    ),
                ),
            )

        assertEquals(true, loaded.rows.single().isDeclined)
    }

    @Test
    fun `displayLabel is the number for a declined seat and the name otherwise`() {
        // [BR2.3, ADR-012, NFR14.28]. The name is RETAINED -- it is the
        // teacher's own record of who they meant to add -- and it is
        // not DISPLAYED, because it names a person who has said the
        // seat is not theirs. Retention and display are different
        // decisions and only the first keeps the name.
        val declined =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    "Physics",
                    listOf(
                        row(
                            "dormant",
                            studentState = "declined",
                            guardianPhone = "01711-234567",
                            displayName = "Rahim",
                        ),
                    ),
                ),
            )
        val accepted =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    "Physics",
                    listOf(
                        row(
                            "active",
                            studentState = "accepted",
                            guardianPhone = "01711-234567",
                            displayName = "Rahim",
                        ),
                    ),
                ),
            )

        assertEquals("01711-234567", declined.rows.single().displayLabel)
        assertEquals("Rahim", accepted.rows.single().displayLabel)
        // The name is retained on the row even when not displayed.
        assertEquals("Rahim", declined.rows.single().displayName)
    }

    @Test
    fun `a declined seat with no number recorded does not fall back to the name`() {
        // **BR2.3's own stated violation is "a name is displayed for a
        // person who has said the seat is not theirs"**, and it makes
        // no exception for having nothing else to show. `guardianPhone`
        // is nullable, so a student-side decline on a seat with no
        // guardian recorded reaches this branch -- which is why the
        // mapper returns null here and the screen renders a
        // placeholder rather than the name.
        val loaded =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    "Physics",
                    listOf(
                        row(
                            "dormant",
                            studentState = "declined",
                            guardianPhone = null,
                            displayName = "Rahim",
                        ),
                    ),
                ),
            )

        assertNull(loaded.rows.single().displayLabel)
    }

    @Test
    fun `a missing guardian link is absent, never pending`() {
        // [BR2.2]. `absent` is a fourth VALUE and not a null: a
        // decision nobody was asked for is not an outstanding one.
        val loaded =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    "Physics",
                    listOf(row("dormant", guardianState = "absent")),
                ),
            )

        assertEquals(LinkState.ABSENT, loaded.rows.single().guardianState)
    }

    @Test
    fun `a split seat carries both states separately`() {
        // [BR2.1, AC1.10.7]. The case the previous response shape could
        // not express: the student is enrolled and owes a fee, the
        // guardian simply does not watch, and either single value for
        // the seat is wrong.
        val loaded =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    "Physics",
                    listOf(
                        row(
                            "active",
                            studentState = "accepted",
                            guardianState = "declined",
                        ),
                    ),
                ),
            )

        val single = loaded.rows.single()
        assertEquals(LinkState.ACCEPTED, single.studentState)
        assertEquals(LinkState.DECLINED, single.guardianState)
    }

    @Test
    fun `isRemovable is read from the server, not derived from the states`() {
        // [BR3.1, NFR14.31]. **The discriminating case**: both
        // decisions read `pending`, so every client-side derivation
        // would say removable. The server says no, because the seat
        // carries an erasure marker this row never sees. A derivation
        // would offer the action and the server would then refuse it.
        val erased =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    "Physics",
                    listOf(
                        row(
                            "dormant",
                            studentState = "pending",
                            guardianState = "absent",
                            isRemovable = false,
                        ),
                    ),
                ),
            )

        val single = erased.rows.single()
        assertEquals(LinkState.PENDING, single.studentState)
        assertEquals(false, single.isRemovable)
    }

    @Test
    fun `an unknown link state fails loudly rather than defaulting`() {
        // Same rule the status enum already follows. Every default here
        // is a lie about somebody's answer: rendering a declined seat
        // as pending invites a teacher to wait for an answer that has
        // already arrived.
        val state =
            RosterStateMapper.afterLoad(
                "Physics",
                listOf(row("active", studentState = "withdrawn")),
            )

        val failed = assertIs<RosterUiState.Failed>(state)
        assertEquals(RosterStateMapper.UNEXPECTED_KEY, failed.messageKey)
    }

    @Test
    fun `a student link reporting absent is refused`() {
        // A seat always HAS a student link -- that is what the seat is
        // -- so `absent` there is a contract failure rather than a seat
        // to render as something.
        val state =
            RosterStateMapper.afterLoad(
                "Physics",
                listOf(row("dormant", studentState = "absent")),
            )

        assertIs<RosterUiState.Failed>(state)
    }

    @Test
    fun `the counts are carried from the server, never counted from rows`() {
        // [BR1.2, BR1.3, NFR20.9]. Arranged so a client tally would
        // give a DIFFERENT answer: three rows, none of them accepted,
        // against a server count of 9 of 12. A mapper counting rows
        // would report 0 of 3 and look perfectly reasonable.
        val loaded =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad(
                    batchName = "Physics",
                    rows =
                        listOf(
                            row("dormant", enrollmentId = "e-1"),
                            row("dormant", enrollmentId = "e-2"),
                            row("dormant", enrollmentId = "e-3"),
                        ),
                    accepted = AcceptedCount(accepted = 9, total = 12),
                ),
            )

        assertEquals(AcceptedCount(9, 12), loaded.accepted)
    }

    @Test
    fun `a roster read carrying no counts renders none rather than zeroes`() {
        // "0 of 0" is a claim about the batch. A read that did not
        // carry the summary has no claim to make.
        val loaded =
            assertIs<RosterUiState.Loaded>(
                RosterStateMapper.afterLoad("Physics", listOf(row("dormant"))),
            )

        assertEquals(null, loaded.accepted)
    }

    @Test
    fun `the two refusals map to two different remedies`() {
        // [BR3.2, NFR23.5]. **Tested as a PAIR.** A test asserting "the
        // removal was refused" passes for both and distinguishes
        // neither; the remedies are what differ, and a teacher shown
        // the wrong one tries something that cannot work.
        val row = uiRow()

        val claimed =
            RosterStateMapper.afterRemovalRefused(
                row,
                envelope("ENROLLMENT_CLAIMED", "enrollment.remove.claimed"),
            )
        val erased =
            RosterStateMapper.afterRemovalRefused(
                row,
                envelope("ENROLLMENT_ERASED", "enrollment.remove.erased"),
            )

        val claimedState = assertIs<RosterUiState.RemovalRefused>(claimed)
        val erasedState = assertIs<RosterUiState.RemovalRefused>(erased)
        assertEquals(RemovalRemedy.MARK_INACTIVE, claimedState.remedy)
        assertEquals(RemovalRemedy.NONE, erasedState.remedy)
        // The pair is distinguishable on BOTH halves a screen reads.
        assertEquals(true, claimedState.remedy != erasedState.remedy)
        assertEquals(true, claimedState.messageKey != erasedState.messageKey)
    }

    @Test
    fun `an unrecognised refusal code does not guess a remedy`() {
        // Telling a teacher to mark a seat inactive when that is not
        // the remedy is worse than telling them nothing.
        val state =
            RosterStateMapper.afterRemovalRefused(
                uiRow(),
                envelope("SOMETHING_NEW", "error.unexpected"),
            )

        assertIs<RosterUiState.Failed>(state)
    }

    @Test
    fun `confirming a removal names the seat being removed`() {
        // [W4]. The confirmation names what is being removed rather
        // than asking "are you sure?" about nothing in particular.
        val row = uiRow()

        val state = RosterStateMapper.beforeRemoval(row)

        val confirming = assertIs<RosterUiState.ConfirmingRemoval>(state)
        assertEquals(row, confirming.row)
    }

    private fun uiRow(): RosterRow =
        RosterRow(
            enrollmentId = "e-1",
            displayName = "Rahim",
            statusLabel = "roster.status.dormant",
            fee = null,
            guardianPhone = null,
            studentState = LinkState.PENDING,
            guardianState = LinkState.ABSENT,
            displayLabel = "Rahim",
            isDeclined = false,
            isRemovable = true,
        )

    private fun envelope(code: String, messageKey: String): ErrorEnvelope =
        ErrorEnvelope(
            ErrorBody(code = code, retryable = false, messageKey = messageKey),
        )
}
