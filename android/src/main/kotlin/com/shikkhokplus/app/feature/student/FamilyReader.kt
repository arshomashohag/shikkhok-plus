package com.shikkhokplus.app.feature.student

/**
 * Who is reading a batch's family view.
 *
 * A student and a guardian read the same shape over two server paths,
 * each resolving its own lens [BR7.2], so the screen never guesses
 * which it is.
 */
enum class FamilyReader {
    /** A student reading their own seat. */
    SELF,

    /** A guardian reading a child's seat. */
    GUARDIAN,
}
