package com.shikkhokplus.app.navigation

import com.shikkhokplus.app.core.network.WorkspaceDto
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.feature.profile.ui.MoreActions
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Which More rows each lens is offered, and where they lead (T9, S4, G4).
 *
 * **The containment check, for More.** Payment methods and money
 * reports resolve a TeacherLens; offering either to a student or a
 * guardian would put a guaranteed refusal one tap away.
 */
class MoreActionsTest {

    private fun opened(lens: Lens?): Pair<MoreActions, MutableList<String>> {
        val routes = mutableListOf<String>()
        return moreActionsFor(lens, MoreActions(), navigate = { routes += it }) to routes
    }

    @Test
    fun `a teacher gets where students pay, the reports and spending, and nothing for families`() {
        val (actions, routes) = opened(Lens.TEACHER)

        assertNotNull(actions.onPaymentMethods).invoke()
        assertNotNull(actions.onCollections).invoke()
        assertNotNull(actions.onExpenses).invoke()
        assertNotNull(actions.onMoneySummary).invoke()
        assertNotNull(actions.onOpenCentre).invoke()
        assertNotNull(actions.onCentreOffers).invoke()
        // Outside a centre there are no members or staff to manage.
        assertNull(actions.onCentreMembers)
        assertNull(actions.onCentreStaff)
        assertNull(actions.onCentreTimetable)
        assertNull(actions.onCentrePayroll)

        assertEquals(
            listOf(
                Destination.PaymentMethods.route,
                Destination.Collections.route,
                Destination.Expenses.route,
                Destination.MoneySummary.route,
                Destination.OpenCentre.route,
                Destination.CentreOffers.route,
            ),
            routes,
        )
        assertNull(actions.onInvitations)
        assertNull(actions.onMyChildren)
    }

    @Test
    fun `a student gets invitations and no teacher rows`() {
        val (actions, routes) = opened(Lens.STUDENT)

        assertNotNull(actions.onInvitations).invoke()

        assertEquals(listOf(Destination.Invitations.route), routes)
        assertNull(actions.onPaymentMethods)
        assertNull(actions.onCollections)
        assertNull(actions.onExpenses)
        assertNull(actions.onMoneySummary)
        assertNull(actions.onMyChildren)
    }

    @Test
    fun `a guardian gets invitations and their children`() {
        val (actions, routes) = opened(Lens.GUARDIAN)

        assertNotNull(actions.onInvitations).invoke()
        assertNotNull(actions.onMyChildren).invoke()

        assertEquals(listOf(Destination.Invitations.route, Destination.MyChildren.route), routes)
        assertNull(actions.onPaymentMethods)
    }

    @Test
    fun `a centre teacher gets other centres' offers and nothing of a centre's money`() {
        val (actions, routes) = opened(Lens.CLASS_TEACHER)

        assertNotNull(actions.onCentreOffers).invoke()

        assertEquals(listOf(Destination.CentreOffers.route), routes)
        assertNull(actions.onPaymentMethods)
        assertNull(actions.onCollections)
        assertNull(actions.onExpenses)
        assertNull(actions.onMoneySummary)
        assertNull(actions.onOpenCentre)
        assertNull(actions.onInvitations)
        assertFalse(isFamily(Lens.CLASS_TEACHER), "a centre teacher has a bar")
    }

    @Test
    fun `a lens-free person gets only the account rows`() {
        // Invitations is already their home tab.
        val (actions, _) = opened(null)

        assertNull(actions.onInvitations)
        assertNull(actions.onPaymentMethods)
        assertNotNull(actions.onSignOut)
    }

    @Test
    fun `invitations is a tab only for a person with no lens`() {
        assertTrue(Destination.Invitations.route in routesFor(null))
        listOf(Lens.STUDENT, Lens.GUARDIAN, Lens.TEACHER).forEach { lens ->
            assertTrue(Destination.Invitations.route !in routesFor(lens), "$lens still has an Invitations tab")
        }
    }

    @Test
    fun `students and guardians have no bottom bar, teachers and the lens-free do`() {
        // S1, S4, G1, G4: a family opens More from the profile button.
        assertTrue(isFamily(Lens.STUDENT))
        assertTrue(isFamily(Lens.GUARDIAN))
        assertTrue(!isFamily(Lens.TEACHER))
        assertTrue(!isFamily(null))
    }

    @Test
    fun `a teacher in a centre also gets its members`() {
        val routes = mutableListOf<String>()
        val actions =
            moreActionsFor(
                Lens.TEACHER,
                MoreActions(currentWorkspace = WorkspaceDto("w-centre", "centre", "Udayan")),
                navigate = { routes += it },
            )

        assertNotNull(actions.onCentreMembers).invoke()
        assertNotNull(actions.onCentreStaff).invoke()
        assertNotNull(actions.onCentreTimetable).invoke()
        assertNotNull(actions.onCentrePayroll).invoke()
        assertEquals(
            listOf(
                Destination.CentreMembers.route,
                Destination.CentreStaff.route,
                Destination.CentreTimetable.route,
                Destination.CentrePayroll.route,
            ),
            routes,
        )
    }

    @Test
    fun `every lens, and a person with none, gets the Help centre`() {
        // Asking for help needs no role: the server reads the account's
        // own questions with no lens and no workspace.
        listOf(Lens.TEACHER, Lens.CLASS_TEACHER, Lens.STUDENT, Lens.GUARDIAN, null).forEach { lens ->
            val (actions, routes) = opened(lens)

            assertNotNull(actions.onHelp, "$lens has no Help centre").invoke()

            assertEquals(listOf(Destination.HelpCentre.route), routes, "$lens")
        }
    }
}
