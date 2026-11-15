package com.shikkhokplus.app.core.network

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * `GET /v1/me` as the server sends it, decoded through the app's own
 * [ApiClient.json] from a JSON string [NFR6.1, NFR6.3, NFR9.1].
 *
 * The username flag decides whether the choose-username gate is shown
 * [FR5.2], so its decode is pinned in both directions, and an absent
 * flag reads as not required so an older server never locks every
 * account behind the gate.
 */
class ProfileDtoTest {

    private fun decode(json: String): MeDto = ApiClient.json.decodeFromString(MeDto.serializer(), json)

    @Test
    fun `the username and the flag decode, keeping the casing as stored`() {
        val me = decode("""{"lenses":[],"username":"Nadia_K","username_required":false}""")

        assertEquals("Nadia_K", me.username)
        assertFalse(me.usernameRequired)
    }

    @Test
    fun `a required username decodes with no username`() {
        val me = decode("""{"lenses":[{"kind":"teacher","count":2}],"username":null,"username_required":true}""")

        assertNull(me.username)
        assertTrue(me.usernameRequired)
    }

    @Test
    fun `an absent flag reads as not required`() {
        val me = decode("""{"lenses":[]}""")

        assertNull(me.username)
        assertFalse(me.usernameRequired)
    }

    @Test
    fun `the account never prints its username, contacts or address`() {
        val me =
            decode(
                """{"lenses":[],"username":"sentinel_user_7","phone":"+8801999999999",""" +
                    """"email":"sentinel@example.invalid","address_house":"House 9","username_required":false}""",
            )

        val text = me.toString()
        listOf("sentinel_user_7", "+8801999999999", "sentinel@example.invalid", "House 9").forEach {
            assertFalse(it in text, text)
        }
    }

    @Test
    fun `an unknown field is dropped rather than failing the read`() {
        val me = decode("""{"lenses":[],"username":"rahim_math","username_required":false,"next_thing":1}""")

        assertEquals("rahim_math", me.username)
    }
}
