package com.shikkhokplus.app.core.format

import com.shikkhokplus.app.core.model.Money
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * The numeral rule, in one place.
 *
 * **Numbers the app shows are Latin. Text people typed is shown
 * exactly as typed.** That is the whole rule, and the split matters:
 * money, marks, dates, times, counts, phone numbers and transaction
 * ids are always 0-9 because they are the app's own output; names,
 * topics and notices keep whatever the teacher or owner typed, because
 * they are not. If a topic says `অধ্যায় ৩`, it stays that way — the
 * app never converts digits inside text a person wrote.
 *
 * **Input accepts both digit sets.** A teacher who types names in
 * Bangla stays on the Bangla keyboard, which produces `০-৯`. Making a
 * number field refuse those would mean switching keyboards between
 * fields on the same form, so [parseAmount] takes either and stores a
 * plain number.
 *
 * This is a presentation and parsing concern only: it holds no money
 * arithmetic, so it stays outside `app.money`'s boundary by
 * construction.
 */
object Numerals {

    /** `৳`, U+09F3. Lives in the Bengali Unicode block. */
    private const val TAKA = "৳"

    /** `০` — the base of the Bengali digit range. */
    private const val BENGALI_ZERO = '০'

    /** `৯`. */
    private const val BENGALI_NINE = '৯'

    /** A local number is 11 digits: `01711234567`. */
    private const val LOCAL_PHONE_LENGTH = 11

    /** The operator prefix, before the dash: `01711`. */
    private const val PHONE_PREFIX_LENGTH = 5

    /**
     * Render an amount for display.
     *
     * The sign goes before the amount with no space, grouped by lakh,
     * and **never with decimals** — 2dp is stored, not shown. A value
     * carrying paisa is rounded half-up to match the money module's
     * single rounding mode, so a displayed total and a computed one
     * cannot disagree by a rounding convention.
     *
     * @param value The amount
     * @return The amount as `৳1,25,400`
     */
    fun money(value: Money): String {
        val whole = value.amount.setScale(0, RoundingMode.HALF_UP)
        return TAKA + groupByLakh(whole.abs().toPlainString()).let {
            if (whole.signum() < 0) "-$it" else it
        }
    }

    /**
     * Group digits the way a Bangladeshi reader parses them.
     *
     * Three from the right, then twos: `125400` becomes `1,25,400`.
     * Western grouping would give `125,400`, which reads as a
     * different magnitude to the person checking it.
     *
     * @param digits The unsigned digits
     * @return The grouped digits
     */
    private fun groupByLakh(digits: String): String {
        if (digits.length <= 3) return digits
        val last3 = digits.takeLast(3)
        val rest = digits.dropLast(3)
        // Chunk from the right by reversing first, then put the groups
        // back in reading order and un-reverse the digits inside each.
        val leadingGroups = rest.reversed()
            .chunked(2)
            .map { it.reversed() }
            .reversed()
        return (leadingGroups + last3).joinToString(",")
    }

    /**
     * Parse a typed amount, in either digit set.
     *
     * Grouping separators and surrounding whitespace are discarded, so
     * a pasted `1,25,400` works. A currency sign is accepted and
     * ignored for the same reason.
     *
     * @param typed What the user typed
     * @return The amount, or null when the text is not a number
     */
    fun parseAmount(typed: String): BigDecimal? {
        val normalised = typed
            .filter { it.isDigit() || isBengaliDigit(it) || it == '.' }
            .map { if (isBengaliDigit(it)) toLatinDigit(it) else it }
            .joinToString("")
        if (normalised.isEmpty() || normalised == ".") return null
        return runCatching { BigDecimal(normalised) }.getOrNull()
    }

    /**
     * Render a mark out of a total.
     *
     * A half mark is kept, a trailing zero is not: `47.5 / 50` and
     * `47 / 50`. Showing `47.0` invites the reader to wonder what the
     * precision means.
     *
     * @param scored The mark scored
     * @param outOf The total available
     * @return The mark as `47.5 / 50`
     */
    fun marks(scored: BigDecimal, outOf: Int): String =
        "${scored.stripTrailingZeros().toPlainString()} / $outOf"

    /**
     * Render a phone number.
     *
     * Grouped after the operator prefix. A country code is dropped,
     * since every number in this product is Bangladeshi and the code
     * is noise on a roster row.
     *
     * **An unexpected length is returned as given.** A number that
     * looks odd is better than one silently reshaped into something
     * the owner did not type — and a wrong guess here would be a wrong
     * identity, since the number *is* the account.
     *
     * @param raw The stored or typed number
     * @return The number as `01711-234567`, or unchanged
     */
    fun phone(raw: String): String {
        val digits = raw
            .filter { it.isDigit() || isBengaliDigit(it) }
            .map { if (isBengaliDigit(it)) toLatinDigit(it) else it }
            .joinToString("")
        val local = digits.removePrefix("880").let {
            if (it.length == LOCAL_PHONE_LENGTH - 1 && !it.startsWith("0")) "0$it" else it
        }
        if (local.length != LOCAL_PHONE_LENGTH) return raw
        return local.take(PHONE_PREFIX_LENGTH) + "-" + local.drop(PHONE_PREFIX_LENGTH)
    }

    /**
     * Normalise a transaction id.
     *
     * Upper-cased with spaces removed, because it arrives pasted from
     * a bKash or Nagad SMS where the casing and spacing vary.
     *
     * @param raw The pasted id
     * @return The id as `BJK40OQ1IL`
     */
    fun transactionId(raw: String): String =
        raw.filterNot { it.isWhitespace() }.uppercase()

    /**
     * Pass text through untouched.
     *
     * Exists to be called rather than to do anything: a call site that
     * routes a name or a topic through here states that it knows the
     * text is a person's and must not be converted. Without it, the
     * rule is invisible at the point it matters.
     *
     * @param typed The text a person wrote
     * @return The same text
     */
    fun freeText(typed: String): String = typed

    private fun isBengaliDigit(c: Char): Boolean =
        c in BENGALI_ZERO..BENGALI_NINE

    private fun toLatinDigit(c: Char): Char =
        '0' + (c - BENGALI_ZERO)
}
