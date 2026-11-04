package com.shikkhokplus.app.navigation

import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.feature.profile.ui.MoreActions
import kotlin.test.Test
import kotlin.test.assertEquals
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
    fun `a teacher gets where students pay and the reports, and nothing for families`() {
        val (actions, routes) = opened(Lens.TEACHER)

        assertNotNull(actions.onPaymentMethods).invoke()
        assertNotNull(actions.onCollections).invoke()

        assertEquals(listOf(Destination.PaymentMethods.route, Destination.Collections.route), routes)
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
}
