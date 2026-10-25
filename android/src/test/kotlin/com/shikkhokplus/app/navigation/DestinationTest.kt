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

    @Test
    fun `every route is distinct`() {
        // Two destinations sharing a route means one is unreachable,
        // and NavHost reports nothing: the first registration wins.
        val routes =
            listOf(
                Destination.Auth,
                Destination.Signup,
                Destination.Batches,
                Destination.CreateBatch,
                Destination.Roster,
                Destination.AddStudent,
            ).map { it.route }

        assertEquals(routes.size, routes.toSet().size, "routes must be unique")
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
}
