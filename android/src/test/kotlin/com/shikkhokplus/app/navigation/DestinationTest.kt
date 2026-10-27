package com.shikkhokplus.app.navigation

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The route patterns, which are the part of a graph that can be wrong
 * silently.
 *
 * **Why these exist rather than a test of the NavHost.** A route built
 * by interpolating at the call site drifts from the pattern the host
 * registered, and the symptom is a destination that simply never
 * opens — no crash, no log. These assert that the `of` builders
 * produce something the registered pattern can match, which is the
 * one property the composable cannot be asked about from bytecode.
 */
class DestinationTest {

    /**
     * Every destination, enumerated from the sealed hierarchy.
     *
     * **Not a hand-written list, deliberately.** The earlier version
     * of this test listed eight destinations by name, so adding a
     * ninth and forgetting to list it meant the new route was never
     * checked — the same shape of gap as a screen with no route.
     * Reflecting over the nested types means a destination cannot
     * opt out of these assertions by being forgotten.
     *
     * **Java reflection, not `sealedSubclasses`.** The Kotlin form
     * needs `kotlin-reflect` on the classpath, and adding a reflection
     * library to the app so a test can enumerate is the wrong trade:
     * every destination is a nested `data object`, so its
     * `INSTANCE` field is already there to read.
     *
     * @return Every destination object
     */
    private fun allDestinations(): List<Destination> =
        Destination::class.java.declaredClasses
            .mapNotNull { nested ->
                runCatching { nested.getDeclaredField("INSTANCE").get(null) }
                    .getOrNull() as? Destination
            }

    @Test
    fun `the enumeration actually finds the destinations`() {
        // A reflection helper that silently returns an empty list
        // would make every test below pass vacuously, which is worse
        // than no test at all.
        // 18 today. A floor rather than an equality: adding a
        // destination should not fail this test, only removing the
        // reflection that finds them should.
        val found = allDestinations()
        assertTrue(found.size >= 18, "expected the full set, found ${found.size}")
        assertTrue(found.contains(Destination.Auth))
        assertTrue(found.contains(Destination.Profile))
    }

    @Test
    fun `every route is distinct`() {
        // Two destinations sharing a route means one is unreachable,
        // and NavHost reports nothing: the first registration wins.
        val routes = allDestinations().map { it.route }

        assertEquals(routes.size, routes.toSet().size, "routes must be unique")
    }

    @Test
    fun `no route is blank or absolute`() {
        allDestinations().forEach {
            assertTrue(it.route.isNotBlank(), "a blank route matches nothing")
            assertTrue(
                !it.route.startsWith("/"),
                "a leading slash makes the route unmatchable: ${it.route}",
            )
        }
    }

    @Test
    fun `every built route substitutes every placeholder`() {
        // **The failure mode this file names in its own header**: a
        // builder that leaves `{arg}` in place produces a route the
        // host cannot match, and the symptom is a screen that never
        // opens, with no crash and no log.
        val built =
            listOf(
                Destination.Sessions.of("b-1", "Class 9"),
                Destination.Attendance.of("s-1"),
                Destination.Exams.of("b-1", "Class 9"),
                Destination.MarkEntry.of("x-1"),
                Destination.Marksheet.of("x-1", "e-1", "SELF"),
                Destination.Progress.of("e-1"),
                Destination.FeeHistory.of("e-1", "GUARDIAN"),
            )

        built.forEach {
            assertTrue("{" !in it, "no placeholder may survive: $it")
        }
    }

    @Test
    fun `a reader-carrying route keeps the reader readable`() {
        // The reader decides which SERVER path is called, and each
        // resolves a different lens [BR7.2]. A route that dropped it
        // would send every caller down one lens's path.
        assertTrue(
            Destination.Marksheet.of("x-1", "e-1", "CHILD").endsWith("reader=CHILD"),
        )
        assertTrue(
            Destination.FeeHistory.of("e-1", "TEACHER").endsWith("reader=TEACHER"),
        )
    }

    @Test
    fun `the roster route carries both arguments it declares`() {
        // The pattern declares {batchId} and {batchName}; a builder
        // that filled only one would navigate to a route the host
        // cannot match.
        assertTrue(Destination.Roster.route.contains("{${Destination.Roster.ARG_ID}}"))
        assertTrue(Destination.Roster.route.contains("{${Destination.Roster.ARG_NAME}}"))
    }

    @Test
    fun `a built roster route substitutes the id`() {
        val built = Destination.Roster.of(id = "b-42", name = "Physics")
        assertTrue(built.startsWith("batches/b-42/roster"), built)
        assertTrue("{" !in built, "no placeholder may survive: $built")
    }

    @Test
    fun `a batch name with a space survives the route`() {
        // **The case that breaks an unencoded route.** "Class 9
        // Physics" contains spaces, and a raw interpolation produces a
        // route the matcher splits — so the roster opens with a
        // truncated title, or not at all.
        val built = Destination.Roster.of(id = "b-1", name = "Class 9 Physics")
        assertTrue(" " !in built, "a space must not reach the route: $built")
        assertTrue(built.contains("Class"), built)
    }

    @Test
    fun `a batch name with an ampersand survives the route`() {
        // An ampersand is the query separator. Unencoded, everything
        // after it becomes a different argument and the name is cut.
        val built = Destination.Roster.of(id = "b-1", name = "Maths & Science")
        val query = built.substringAfter("name=")
        assertTrue("&" !in query, "an ampersand must be encoded: $built")
    }

    @Test
    fun `the add-student route substitutes the batch id`() {
        val built = Destination.AddStudent.of("b-7")
        assertEquals("batches/b-7/roster/add", built)
    }

    @Test
    fun `the four tab destinations have plain routes with no arguments`() {
        // A tab is switched to, never pushed with a payload. A route
        // carrying `{arg}` could not be reached from the bar at all,
        // and the failure would be silent: the tab simply would not
        // open.
        listOf(
            Destination.Overview,
            Destination.Batches,
            Destination.Dues,
            Destination.Profile,
        ).forEach {
            assertTrue("{" !in it.route, "a tab route takes no argument: ${it.route}")
            assertTrue("?" !in it.route, "a tab route takes no query: ${it.route}")
        }
    }
}
