package com.shikkhokplus.app.core.model

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * An exact monetary amount in Bangladeshi Taka.
 *
 * A value class over [BigDecimal], so a `Double` cannot be assigned where a
 * `Money` is expected — the compiler stops it, with no custom lint rule at
 * all. That is the point: review depth on this surface is limited, so the
 * boundary has to be mechanical.
 *
 * The client performs **no money arithmetic**. Every balance, status and
 * total is computed server-side and rendered here. This type exists to carry
 * a value across the wire without losing precision, and to make losing it a
 * compile error rather than a runtime surprise.
 *
 * Always exactly two decimal places, matching the server's canonical form.
 *
 * **The serializer is attached to the TYPE, not to each field**, which is
 * the same chokepoint principle the backend's column type uses. A
 * per-field `@Serializable(with = ...)` works until one DTO forgets it,
 * and a forgotten annotation is invisible in review because the field
 * still renders — it just renders a number. Attaching it here means a
 * money field cannot be declared without it.
 *
 * @property amount The exact value, scaled to two decimal places.
 */
@JvmInline
@kotlinx.serialization.Serializable(with = MoneySerializer::class)
value class Money(val amount: BigDecimal) {

    init {
        require(amount.scale() == SCALE) {
            "Money must carry exactly $SCALE decimal places, got " +
                "${amount.scale()} in $amount. Construct via Money.of()."
        }
    }

    /** Render the canonical wire form: two decimals, no sign, Latin digits. */
    override fun toString(): String = amount.toPlainString()

    companion object {
        /** Every money value carries exactly two decimal places. */
        const val SCALE: Int = 2

        /**
         * The canonical wire form the server emits and this client accepts.
         * Note the absence of a sign: the pattern admits none.
         */
        val WIRE_PATTERN: Regex = Regex("""^[0-9]+\.[0-9]{2}$""")

        /** Zero, so no caller writes a bare `0` in a comparison. */
        val ZERO: Money = Money(BigDecimal.ZERO.setScale(SCALE))

        /**
         * Build from a canonical wire string.
         *
         * @param raw A string in canonical form.
         * @return The parsed amount.
         * @throws IllegalArgumentException If the string is not canonical.
         *   Rejected loudly rather than coerced: a lenient parse is the
         *   actual failure mode, and it passes a happy-path test on both
         *   sides while the value is already wrong.
         */
        fun of(raw: String): Money {
            require(WIRE_PATTERN.matches(raw)) {
                "'$raw' is not in canonical money form: exactly two decimal " +
                    "places, no sign, no separator, Latin digits only."
            }
            return Money(BigDecimal(raw).setScale(SCALE, RoundingMode.UNNECESSARY))
        }

        /**
         * Read an amount a person TYPED, or null when it is not one.
         *
         * **Deliberately not [of].** That function parses the wire and
         * must stay strict. This one reads a text field, where `1500`,
         * `1,500`, `১৫০০` and `৳1500` all mean the same amount and none
         * of them is canonical. Sending them as typed is the defect
         * this exists to close: the server refused every one, and a
         * teacher's class was silently never created.
         *
         * **Representation only, never arithmetic.** It maps Bangla
         * digits, drops separators and a taka sign, and pads to two
         * places. It refuses rather than rounds a third decimal: the
         * rounding mode is declared once on the server [D-20], and a
         * client that rounded would be a second declaration.
         *
         * Blank returns null like any non-amount. What blank MEANS --
         * inherit the class fee -- is the caller's decision, and
         * returning [ZERO] here would waive the fee instead.
         *
         * @param raw The text as typed
         * @return The amount, or null when the text is not an amount
         */
        fun fromTyped(raw: String): Money? {
            val latin =
                raw
                    .trim()
                    .removePrefix(TAKA_SIGN)
                    .trim()
                    .map(::latinDigit)
                    .joinToString("")
            if (!TYPED_PATTERN.matches(latin)) return null

            val plain = latin.replace(",", "")
            return try {
                Money(BigDecimal(plain).setScale(SCALE, RoundingMode.UNNECESSARY))
            } catch (_: ArithmeticException) {
                null
            }
        }

        /** The taka sign a person may type before an amount. */
        private const val TAKA_SIGN: String = "৳"

        /** Bangla digit zero, U+09E6; the nine that follow are contiguous. */
        private const val BANGLA_ZERO: Char = '০'

        /** The offsets of the ten digits from zero, in either script. */
        private val DIGIT_OFFSETS: IntRange = 0..9

        /**
         * What a typed amount may look like once its digits are Latin:
         * digits with optional comma groups, then up to two decimals.
         * The comma rule admits both the Western `1,500,000` and the
         * South Asian `15,00,000` grouping, and refuses a leading or
         * trailing comma.
         */
        private val TYPED_PATTERN: Regex =
            Regex("""^[0-9]+(,[0-9]+)*(\.[0-9]{1,2})?$""")

        /**
         * Map one Bangla digit to its Latin counterpart.
         *
         * @param char Any character
         * @return The Latin digit, or the character unchanged
         */
        private fun latinDigit(char: Char): Char {
            val offset = char - BANGLA_ZERO
            return if (offset in DIGIT_OFFSETS) '0' + offset else char
        }
    }
}
