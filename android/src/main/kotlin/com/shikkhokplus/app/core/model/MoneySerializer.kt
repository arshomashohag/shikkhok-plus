package com.shikkhokplus.app.core.model

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerializationException
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.JsonDecoder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive

/**
 * Reads a money value from a JSON **string**, and from nothing else.
 *
 * A JSON number is rejected loudly rather than coerced, and that choice is
 * the whole reason this class exists. JSON numbers are IEEE 754 doubles in
 * most parsers, so accepting one would convert the value to a float on this
 * side of the wire — reintroducing exactly the representation error the
 * server's money type exists to prevent, where none of its controls reach.
 *
 * The dangerous implementation is the lenient one: a decoder that quietly
 * accepts a number and converts it passes a happy-path test on both sides
 * while the value is already wrong. That is why [deserialize] inspects the
 * JSON primitive's `isString` flag rather than simply calling `.content`,
 * which would succeed on a number.
 */
object MoneySerializer : KSerializer<Money> {

    override val descriptor: SerialDescriptor =
        PrimitiveSerialDescriptor("Money", PrimitiveKind.STRING)

    /**
     * Write the canonical wire form.
     *
     * @param encoder The target encoder.
     * @param value The amount to write.
     */
    override fun serialize(encoder: Encoder, value: Money) {
        encoder.encodeString(value.toString())
    }

    /**
     * Read an amount, refusing anything that is not a canonical string.
     *
     * @param decoder The source decoder.
     * @return The parsed amount.
     * @throws SerializationException If the field is a JSON number rather
     *   than a string, or is a string not in canonical form.
     */
    override fun deserialize(decoder: Decoder): Money {
        val jsonDecoder = decoder as? JsonDecoder
            ?: return parseOrThrow(decoder.decodeString())

        val primitive: JsonPrimitive = jsonDecoder.decodeJsonElement().jsonPrimitive
        if (!primitive.isString) {
            throw SerializationException(
                "A money field must arrive as a JSON string, not a number " +
                    "(got ${primitive.content}). A decoder that quietly " +
                    "converts a number is the actual failure mode, and it " +
                    "passes a happy-path test on both sides."
            )
        }
        return parseOrThrow(primitive.content)
    }

    /**
     * Parse a canonical string, converting a rejection into a
     * serialization failure.
     *
     * @param raw The string to parse.
     * @return The parsed amount.
     * @throws SerializationException If the string is not canonical.
     */
    private fun parseOrThrow(raw: String): Money =
        try {
            Money.of(raw)
        } catch (e: IllegalArgumentException) {
            throw SerializationException(e.message ?: "Malformed money value", e)
        }
}
