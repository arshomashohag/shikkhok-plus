package com.shikkhokplus.app.navigation

import com.shikkhokplus.app.core.session.Lens
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Where each lens lands, and what its bar reaches.
 *
 * **The gap this closes.** Every signed-in person was sent to
 * `Batches`, whose endpoint requires a `TeacherLens` — so the app
 * opened on an endpoint that refused two of its three audiences, and
 * nothing failed loudly enough to notice.
 */
class LensRoutingTest {

    private val everyLens = listOf(Lens.TEACHER, Lens.STUDENT, Lens.GUARDIAN, null)

    @Test
    fun `a teacher lands on their classes`() {
        assertEquals(Destination.Batches.route, homeFor(Lens.TEACHER))
    }

    @Test
    fun `a guardian lands on their children, never on a teacher screen`() {
        // `/v1/batches` resolves a TeacherLens and refuses a guardian.
        val home = homeFor(Lens.GUARDIAN)
        assertEquals(Destination.GuardianHome.route, home)
        assertTrue(home != Destination.Batches.route)
    }

    @Test
    fun `a student does not land on a teacher screen`() {
        assertTrue(homeFor(Lens.STUDENT) != Destination.Batches.route)
    }

    @Test
    fun `a student lands on their own batches`() {
        assertEquals(Destination.MyBatches.route, homeFor(Lens.STUDENT))
    }

    @Test
    fun `no lens lands somewhere that works without one`() {
        // **The fresh-signup case.** Invitations is lens-exempt on the
        // server for exactly this reason [BR1.3]: it is the route that
        // REPORTS which seats exist, so requiring a lens would mean
        // needing one to find out you have none.
        assertEquals(Destination.Invitations.route, homeFor(null))
    }

    @Test
    fun `every lens has a home that is one of its own tabs`() {
        // A home outside the bar leaves the first screen with no tab
        // highlighted, which reads as a broken bar.
        everyLens.forEach { lens ->
            assertTrue(
                homeFor(lens) in routesFor(lens),
                "the home for $lens is not in its own bar",
            )
        }
    }

    @Test
    fun `every bar can reach the profile`() {
        // Profile is where account deletion and switching live, so a
        // lens that could not reach it would strand someone.
        everyLens.forEach { lens ->
            assertTrue(
                Destination.Profile.route in routesFor(lens),
                "$lens cannot reach the profile",
            )
        }
    }

    @Test
    fun `no bar offers the same route twice`() {
        everyLens.forEach { lens ->
            val routes = routesFor(lens)
            assertEquals(
                routes.size,
                routes.toSet().size,
                "$lens has a duplicated tab",
            )
        }
    }

    @Test
    fun `only a teacher's bar offers teacher-only screens`() {
        // **The containment check.** Batches, Overview and Dues all
        // resolve a TeacherLens; offering one on another lens's bar
        // would put a guaranteed refusal one tap from the home screen.
        val teacherOnly =
            setOf(
                Destination.Batches.route,
                Destination.Today.route,
                Destination.Dues.route,
            )

        listOf(Lens.STUDENT, Lens.GUARDIAN, null).forEach { lens ->
            val offending = routesFor(lens).filter { it in teacherOnly }
            assertEquals(emptyList(), offending, "$lens is offered $offending")
        }
    }

    @Test
    fun `a tab index round-trips to its own route`() {
        // The bar and the routes are paired BY POSITION, so index 2 in
        // one must be index 2 in the other. This is the pairing that
        // breaks silently: a mismatch opens the wrong screen rather
        // than failing.
        everyLens.forEach { lens ->
            routesFor(lens).forEachIndexed { index, route ->
                assertEquals(
                    index,
                    tabIndexOf(lens, route),
                    "$lens tab $index does not round-trip",
                )
            }
        }
    }

    @Test
    fun `a route outside the bar highlights nothing`() {
        // Correct for a pushed screen that happens to render a bar:
        // highlighting a tab the person is not on would be a lie.
        assertEquals(-1, tabIndexOf(Lens.STUDENT, Destination.Batches.route))
    }

    @Test
    fun `every tab route is a registered destination`() {
        // A bar entry pointing at a route no destination declares is
        // a tab that does nothing when tapped.
        val declared =
            Destination::class.java.declaredClasses
                .mapNotNull { nested ->
                    runCatching { nested.getDeclaredField("INSTANCE").get(null) }
                        .getOrNull() as? Destination
                }
                .map { it.route }
                .toSet()

        everyLens.forEach { lens ->
            routesFor(lens).forEach {
                assertTrue(it in declared, "$it is not a declared destination")
            }
        }
    }
}
