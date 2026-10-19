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
    }
}
