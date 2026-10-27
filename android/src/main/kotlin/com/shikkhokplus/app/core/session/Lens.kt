package com.shikkhokplus.app.core.session

import com.shikkhokplus.app.core.network.LensEntryDto

/**
 * A lens this account can take [TC-11, D-2].
 *
 * **A closed set, parsed from the server's string.** The wire carries
 * `teacher`, `student` or `guardian`; a value outside that set is a
 * server the client does not understand, and the honest answer is to
 * drop it rather than invent a fourth role on the device.
 *
 * **This is a VIEW selector, never an authorization fact.** The server
 * resolves the real lens per request from owned batches and
 * enrollments, so choosing `TEACHER` here opens teacher screens and
 * nothing more: a student who somehow selected it would be refused by
 * every endpoint behind it. That is the property that makes it safe to
 * keep this choice on the device [TC-11].
 */
enum class Lens {
    /** Runs classes. */
    TEACHER,

    /** Attends classes. */
    STUDENT,

    /** A child's recorded guardian. */
    GUARDIAN,

    ;

    companion object {
        /**
         * Parse one server entry.
         *
         * @param wire The `kind` the server sent
         * @return The lens, or null when it is not one this app knows
         */
        fun parse(wire: String): Lens? =
            entries.firstOrNull { it.name.equals(wire, ignoreCase = true) }
    }
}

/**
 * One lens with how much sits behind it.
 *
 * The count is the server's and is shown on the picker, so a person
 * with two lenses can tell them apart by what each holds rather than
 * by its name alone.
 *
 * @property lens Which lens
 * @property count How many classes, enrollments or children it reaches
 */
data class LensOption(
    val lens: Lens,
    val count: Int,
)

/**
 * Read the server's lens list into the ones this app can open.
 *
 * **Order is preserved, not sorted.** The server documents a fixed
 * order — teacher, then student, then guardian — so the picker does
 * not reshuffle between sign-ins as counts change. Re-sorting here
 * would reintroduce exactly that.
 *
 * An unrecognised `kind` is dropped rather than failing the whole
 * list: a server that adds a fourth lens should leave this app on the
 * three it understands, not sign the person out.
 *
 * @param entries The lenses as the server listed them
 * @return The options this app can open, in the server's order
 */
fun readLenses(entries: List<LensEntryDto>): List<LensOption> =
    entries.mapNotNull { entry ->
        Lens.parse(entry.kind)?.let { LensOption(it, entry.count) }
    }
