package com.shikkhokplus.app.navigation

import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.feature.profile.ProfileSummary
import com.shikkhokplus.app.feature.profile.ui.MoreActions
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue

/**
 * Which sign-in rows More offers, decided from what the server said the
 * account holds, and the account's new fields as they arrive.
 */
class AccountRowsTest {

    private fun summary(phone: String?, email: String?, hasPassword: Boolean = true) =
        ProfileSummary(selfName = "Rafi", address = null, phone = phone, email = email, hasPassword = hasPassword)

    @Test
    fun `an email-only account is offered add phone, and not add email`() {
        val routes = mutableListOf<String>()
        val rows = accountRowsFor(summary(phone = null, email = "rafi@example.com")) { routes += it }

        assertNotNull(rows.onAddPhone).invoke()
        assertNull(rows.onAddEmail)
        assertEquals(listOf("me/contact/phone"), routes)
    }

    @Test
    fun `a phone-only account is offered add email, and not add phone`() {
        val routes = mutableListOf<String>()
        val rows = accountRowsFor(summary(phone = "+8801711111111", email = null)) { routes += it }

        assertNull(rows.onAddPhone)
        assertNotNull(rows.onAddEmail).invoke()
        assertEquals(listOf("me/contact/email"), routes)
    }

    @Test
    fun `nothing read yet offers no add row, because unknown is not absent`() {
        val rows = accountRowsFor(null) {}

        assertNull(rows.onAddPhone)
        assertNull(rows.onAddEmail)
        assertTrue(rows.hasPassword, "an unknown never nags")
    }

    @Test
    fun `the password row carries whether a current password is asked for`() {
        val routes = mutableListOf<String>()
        accountRowsFor(summary("+8801711111111", null, hasPassword = false)) { routes += it }.onPassword()
        accountRowsFor(summary("+8801711111111", null, hasPassword = true)) { routes += it }.onPassword()

        assertEquals(listOf("me/password?has=false", "me/password?has=true"), routes)
    }

    @Test
    fun `the rows reach More's actions, and a missing token store adds none`() {
        val rows = accountRowsFor(summary(phone = null, email = "rafi@example.com", hasPassword = false)) {}

        val withRows = MoreActions().withAccountRows(rows)
        assertNotNull(withRows.onPassword)
        assertFalse(withRows.hasPassword)
        assertNotNull(withRows.onAddPhone)

        val base = MoreActions()
        assertSame(base, base.withAccountRows(null))
    }

    @Test
    fun `the account's email and password flag decode, and an old server reads as having one`() {
        val now =
            ApiClient.json.decodeFromString(
                MeDto.serializer(),
                """{"lenses":[],"phone":null,"email":"rafi@example.com","has_password":false}""",
            )
        assertNull(now.phone)
        assertEquals("rafi@example.com", now.email)
        assertFalse(now.hasPassword)

        // A server from before passwords sends neither field. Reading that
        // as "no password" would prompt every account at once.
        val before = ApiClient.json.decodeFromString(MeDto.serializer(), """{"lenses":[],"phone":"+8801711111111"}""")
        assertNull(before.email)
        assertTrue(before.hasPassword)
    }
}
