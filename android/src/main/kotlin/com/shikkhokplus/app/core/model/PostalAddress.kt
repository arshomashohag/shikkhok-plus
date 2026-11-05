package com.shikkhokplus.app.core.model

/**
 * An address in the four parts sign-up asks for (decided 2026-11-05).
 *
 * **Format only, never policy.** [isComplete] says whether each part is
 * filled in and the postcode is four digits, so the form can enable its
 * button; the server checks the same shape and is the one that decides.
 *
 * @property house House or flat
 * @property road Road or area
 * @property city City or district
 * @property postcode Four digits, Latin or Bangla
 */
data class PostalAddress(
    val house: String = "",
    val road: String = "",
    val city: String = "",
    val postcode: String = "",
) {
    /** Whether every part is filled in and the postcode is four digits. */
    val isComplete: Boolean
        get() = house.isNotBlank() && road.isNotBlank() && city.isNotBlank() && postcodeIsValid(postcode)

    /** The postcode with Bangla digits as Latin ones, as the server stores it. */
    val latinPostcode: String
        get() = latin(postcode.trim())

    /**
     * The parts on one line, for reading back.
     *
     * @return "House 12, Road 5, Dhaka 1205", or null when nothing is filled in
     */
    fun oneLine(): String? {
        val place = listOf(city.trim(), latinPostcode).filter { it.isNotEmpty() }.joinToString(" ")
        return listOf(house.trim(), road.trim(), place).filter { it.isNotEmpty() }.joinToString(", ").ifEmpty { null }
    }

    companion object {
        private const val POSTCODE_DIGITS = 4
        private const val BANGLA_ZERO = '০'

        /**
         * Whether a typed postcode is four digits.
         *
         * @param raw What was typed
         * @return True for four Latin or Bangla digits
         */
        fun postcodeIsValid(raw: String): Boolean {
            val digits = latin(raw.trim())
            return digits.length == POSTCODE_DIGITS && digits.all { it in '0'..'9' }
        }

        /**
         * Bangla digits as Latin ones.
         *
         * @param raw The text
         * @return The same text with Latin digits
         */
        fun latin(raw: String): String =
            raw.map { if (it in BANGLA_ZERO..'৯') '0' + (it - BANGLA_ZERO) else it }.joinToString("")
    }
}
