package com.shikkhokplus.app.feature.profile

import com.shikkhokplus.app.core.model.Money

/**
 * Where deleting one's own account stands (O5).
 *
 * **Separate from the profile's state**, because the two screens are
 * separate: the confirmation is its own destination, and a refusal there
 * must not turn the profile into an error screen.
 */
sealed interface DeletionState {
    /** Nothing under way. */
    data object Idle : DeletionState

    /**
     * Asking the person to type their number back.
     *
     * @property phone The number to match, or null when the profile read
     *   did not return one; confirmation then cannot pass, which is the
     *   safe direction for an action that cannot be undone
     */
    data class Confirming(val phone: String?) : DeletionState

    /** The request is in flight. */
    data object Deleting : DeletionState

    /** The server deleted it. The app must now end the session. */
    data object Deleted : DeletionState

    /**
     * The server refused, or never answered.
     *
     * @property phone The number, kept so the person can try again
     * @property messageKey Names a string resource [TC-15, D-43]
     * @property retryable Read from the server's envelope [TC-9]
     */
    data class Failed(
        val phone: String?,
        val messageKey: String,
        val retryable: Boolean,
    ) : DeletionState
}

/**
 * What a teacher's deletion leaves behind, as the server counted it.
 *
 * @property batchCount Their batches, which stay with their students
 * @property studentCount The students in them
 * @property outstanding What is still recorded as owed, which stays on
 *   those records and can no longer be collected
 */
data class TeacherFootprint(
    val batchCount: Int,
    val studentCount: Int,
    val outstanding: Money,
)

/** How many digits a Bangladeshi mobile number has without its country code. */
private const val LOCAL_NUMBER_DIGITS = 11

/** Bangla digit zero; the nine after it are contiguous. */
private const val BANGLA_ZERO = '০'

/** The offsets of the ten digits from zero, in either script. */
private val DIGIT_OFFSETS = 0..9

/**
 * Whether a typed number names the account's own number.
 *
 * **A confirmation gesture, not an authorization check** -- the access
 * token is the server's proof. It exists so a person cannot delete their
 * account with one stray tap, which is why it is strict: the full local
 * number, eleven digits, in Latin or Bangla digits, with any spaces,
 * dashes or country code ignored.
 *
 * @param typed What the person typed
 * @param phone The account's number, as `GET /v1/me` returned it
 * @return True when they match
 */
fun numberMatches(typed: String, phone: String?): Boolean {
    if (phone == null) return false
    val mine = digitsOf(phone)
    val theirs = digitsOf(typed)
    // At least the full local number, and the END of the stored one:
    // `01611477203` and `8801611477203` both match `+8801611477203`,
    // and a short tail like `477203` does not.
    return theirs.length >= LOCAL_NUMBER_DIGITS && mine.endsWith(theirs)
}

/**
 * Keep only the digits, reading Bangla digits as Latin ones.
 *
 * @param text Any text
 * @return Its digits, in order
 */
private fun digitsOf(text: String): String =
    text.mapNotNull { char ->
        val bangla = char - BANGLA_ZERO
        when {
            char.isDigit() && char in '0'..'9' -> char
            bangla in DIGIT_OFFSETS -> '0' + bangla
            else -> null
        }
    }.joinToString("")
