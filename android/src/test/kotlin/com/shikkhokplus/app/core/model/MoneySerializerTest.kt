package com.shikkhokplus.app.core.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import java.math.BigDecimal
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * The client half of the money boundary.
 *
 * `team.md` requires every money-carrying model class to ship a
 * serialization test proving decode from a JSON string and **loud failure**
 * on a JSON number — because a lenient decoder that quietly accepts a number
 * and converts it is the actual failure mode, and it passes a happy-path
 * both-sides test.
 *
 * These run as local JVM unit tests: no emulator, no device, no signing.
 */
class MoneySerializerTest {

    @Serializable
    private data class FeeResponse(
        @Serializable(with = MoneySerializer::class)
        val outstanding: Money,
    )

    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun `decodes a canonical json string`() {
        val result = json.decodeFromString<FeeResponse>(
            """{"outstanding":"1234.56"}"""
        )
        assertEquals(BigDecimal("1234.56"), result.outstanding.amount)
    }

    @Test
    fun `decodes zero`() {
        val result = json.decodeFromString<FeeResponse>(
            """{"outstanding":"0.00"}"""
        )
        assertTrue(result.outstanding.amount.compareTo(BigDecimal.ZERO) == 0)
    }

    @Test
    fun `fails loudly on a json number`() {
        // THE test. A lenient decoder would accept this, convert through a
        // Double, and be wrong in a way nothing downstream could detect.
        val failure = assertFailsWith<SerializationException> {
            json.decodeFromString<FeeResponse>("""{"outstanding":1234.56}""")
        }
        assertTrue(
            failure.message!!.contains("JSON string"),
            "Expected the refusal to name the cause, got: ${failure.message}"
        )
    }

    @Test
    fun `fails loudly on an integer json number`() {
        assertFailsWith<SerializationException> {
            json.decodeFromString<FeeResponse>("""{"outstanding":1234}""")
        }
    }

    @Test
    fun `fails on a non-canonical string`() {
        assertFailsWith<SerializationException> {
            json.decodeFromString<FeeResponse>("""{"outstanding":"1234.5"}""")
        }
    }

    @Test
    fun `fails on a signed string`() {
        // The canonical pattern admits no sign; a negative reaching the
        // client means a sign rule was violated server-side.
        assertFailsWith<SerializationException> {
            json.decodeFromString<FeeResponse>("""{"outstanding":"-1.00"}""")
        }
    }

    @Test
    fun `fails on bangla digits`() {
        assertFailsWith<SerializationException> {
            json.decodeFromString<FeeResponse>("""{"outstanding":"১২৩৪.৫৬"}""")
        }
    }

    @Test
    fun `encodes back to the canonical form`() {
        val encoded = json.encodeToString(FeeResponse.serializer(), FeeResponse(Money.of("1234.56")))
        assertEquals("""{"outstanding":"1234.56"}""", encoded)
    }

    @Test
    fun `round trips`() {
        val original = FeeResponse(Money.of("9999999999.99"))
        val decoded = json.decodeFromString<FeeResponse>(
            json.encodeToString(FeeResponse.serializer(), original)
        )
        assertEquals(original, decoded)
    }
}
