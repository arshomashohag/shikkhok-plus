package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import java.math.BigDecimal
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * D1's money-carrying DTO, and the width of the lookup response.
 *
 * `team.md` requires **every** money-carrying model class to ship a
 * serialization test proving decode from a JSON string and **loud
 * failure** on a JSON number. [InvitationDto] is D1's, and the loud
 * half is the one that matters: a lenient decoder that quietly accepts
 * a number and converts it is the actual failure mode, and it passes a
 * happy-path both-sides test while the value is already wrong.
 */
class AccountsDtoTest {

    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun `an invitation decodes a fee from a json string`() {
        val dto =
            json.decodeFromString<InvitationDto>(
                """
                {"enrollment_id":"e-1","batch_name":"Physics",
                 "subject":["Physics"],"fee_amount":"1200.00",
                 "decision":"pending","role":"student"}
                """.trimIndent(),
            )

        assertEquals(BigDecimal("1200.00"), dto.feeAmount?.amount)
    }

    @Test
    fun `an invitation refuses a fee sent as a json number`() {
        // **The loud failure.** A decoder that accepted 1200.00 as a
        // double would reintroduce the representation error the whole
        // money boundary exists to prevent, on the client side where
        // none of the server's controls reach [TC-7, D-20].
        val failure =
            assertFailsWith<SerializationException> {
                json.decodeFromString<InvitationDto>(
                    """
                    {"enrollment_id":"e-1","batch_name":"Physics",
                     "subject":["Physics"],"fee_amount":1200.00,
                     "decision":"pending","role":"student"}
                    """.trimIndent(),
                )
            }

        assertTrue(failure.message != null)
    }

    @Test
    fun `a null fee stays null and is not read as zero`() {
        // Null means "inherits the batch default" and zero means
        // "waived". Collapsing them would show a waiver where a seat
        // simply has no override of its own.
        val dto =
            json.decodeFromString<InvitationDto>(
                """
                {"enrollment_id":"e-1","batch_name":"Physics",
                 "subject":["Physics"],"decision":"pending","role":"student"}
                """.trimIndent(),
            )

        assertNull(dto.feeAmount)
    }

    @Test
    fun `an invitation round-trips a fee as a string, never a number`() {
        val encoded =
            json.encodeToString(
                InvitationDto.serializer(),
                InvitationDto(
                    enrollmentId = "e-1",
                    batchName = "Physics",
                    subject = listOf("Physics"),
                    feeAmount = Money.of("1200.00"),
                    decision = "pending",
                    role = "student",
                ),
            )

        assertTrue(
            encoded.contains("\"fee_amount\":\"1200.00\""),
            "the fee crossed the wire as a number: $encoded",
        )
    }

    @Test
    fun `the lookup response declares no teacher and no batch field`() {
        // **The absences are the requirement** [BR2.3, AC1.12.2]. A
        // field declared here is a field somebody will eventually ask
        // the server to fill, so the bound is held on the TYPE rather
        // than on one response's values.
        val declared =
            AlreadyAddedDto.serializer().descriptor.let { descriptor ->
                (0 until descriptor.elementsCount).map(descriptor::getElementName)
            }

        assertEquals(
            listOf("already_added", "display_name", "role"),
            declared,
        )
    }

    @Test
    fun `the lookup tolerates a field a later server adds`() {
        // `/v1/` endpoints stay additive and the app handles unknown
        // fields rather than failing to parse [D-26]. Client and server
        // version independently.
        val dto =
            json.decodeFromString<AlreadyAddedDto>(
                """{"already_added":false,"something_new":"ignored"}""",
            )

        assertEquals(false, dto.alreadyAdded)
    }

    @Test
    fun `a signup response carries no token`() {
        // Signup does not authenticate: the person verifies through the
        // existing OTP flow, which carries the seven abuse controls
        // [BR2.2]. A token here would make signup a second
        // authentication path with none of them.
        val declared =
            SignupResponseDto.serializer().descriptor.let { descriptor ->
                (0 until descriptor.elementsCount).map(descriptor::getElementName)
            }

        assertEquals(listOf("account_id", "code_sent_to"), declared)
    }
}
