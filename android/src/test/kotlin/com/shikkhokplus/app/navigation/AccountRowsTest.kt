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
 * account holds, and the account's fields as they arrive.
 *
 * **Rewritten for U3 from the new acceptance criterion** [W5, W6, Q3]:
 * the two "Add phone" / "Add email" rows became one "Phone and email" row
 * (adding, replacing and removing live on its screen), and a Username row
 * was added. The cases below are the new design's, not the old rows'.
 */
class AccountRowsTest {

    private fun summary(
        phone: String?,
        email: String?,
        hasPassword: Boolean = true,
        username: String? = null,
    ) = ProfileSummary(
        selfName = "Rafi",
        address = null,
        phone = phone,
        email = email,
        hasPassword = hasPassword,
        username = username,
    )

    @Test
    fun `the username row shows the stored name and opens the Username screen`() {
        val routes = mutableListOf<String>()
        val rows = accountRowsFor(summary("+8801711111111", null, username = "Nadia_K")) { routes += it }

        rows.onUsername()

        assertEquals("Nadia_K", rows.username)
        assertEquals(listOf(Destination.Username.route), routes)
    }

    @Test
    fun `no username yet leaves the subtitle to the screen's own words`() {
        assertNull(accountRowsFor(summary("+8801711111111", null)) {}.username)
    }

    @Test
    fun `one contacts row, its line the present contacts, phone first`() {
        val routes = mutableListOf<String>()
        val both = accountRowsFor(summary("+8801711111111", "rafi@example.com")) { routes += it }

        both.onContacts()

        assertEquals("+8801711111111 · rafi@example.com", both.contactsLine)
        assertEquals("rafi@example.com", accountRowsFor(summary(null, "rafi@example.com")) {}.contactsLine)
        assertEquals("+8801711111111", accountRowsFor(summary("+8801711111111", null)) {}.contactsLine)
        assertEquals(listOf(Destination.Contacts.route), routes)
    }

    @Test
    fun `nothing read yet says nothing about the contacts, because unknown is not absent`() {
        val rows = accountRowsFor(null) {}

        assertNull(rows.contactsLine)
        assertNull(rows.username)
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
        val rows = accountRowsFor(summary(null, "rafi@example.com", hasPassword = false, username = "nadia_k")) {}

        val withRows = MoreActions().withAccountRows(rows)
        assertNotNull(withRows.onPassword)
        assertFalse(withRows.hasPassword)
        assertNotNull(withRows.onUsername)
        assertNotNull(withRows.onContacts)
        assertEquals("nadia_k", withRows.username)
        assertEquals("rafi@example.com", withRows.contactsLine)

        val base = MoreActions()
        assertSame(base, base.withAccountRows(null))
    }

    @Test
    fun `the rows never print the name or the contacts`() {
        val sentinels = summary("+8801999999999", "sentinel@example.invalid", username = "sentinel_user_7")
        val rows = accountRowsFor(sentinels) {}

        listOf(rows.toString(), MoreActions().withAccountRows(rows).toString()).forEach { text ->
            listOf("+8801999999999", "sentinel@example.invalid", "sentinel_user_7").forEach {
                assertFalse(it in text, text)
            }
        }
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
