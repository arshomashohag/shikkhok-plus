package com.shikkhokplus.app.feature.account

import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.UsernameChangeDto
import com.shikkhokplus.app.feature.account.FakeAccountRepository.Companion.refused
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse

/**
 * Where each rename answer goes (functional-spec § 4, W5 step 5)
 * [FR7.1, FR7.2, FR11.3]: the client never decides whether a rename is
 * allowed, it only routes the server's answer to a field or a banner.
 */
class UsernameStateMapperTest {

    private val form = UsernameUiState.Editing(current = "nadia_k", saving = true)

    @Test
    fun `a 200 with a date is Changed with that date`() {
        assertEquals(
            UsernameUiState.Changed("Nadia_K", "2026-12-14T10:00:00Z"),
            UsernameStateMapper.afterChange(AuthResult.Ok(UsernameChangeDto("Nadia_K", "2026-12-14T10:00:00Z")), form),
        )
    }

    @Test
    fun `a 200 without a date is Changed without one`() {
        assertEquals(
            UsernameUiState.Changed("Nadia_K", null),
            UsernameStateMapper.afterChange(AuthResult.Ok(UsernameChangeDto("Nadia_K", null)), form),
        )
    }

    @Test
    fun `too soon with a date is a banner naming the server's date`() {
        val state =
            UsernameStateMapper.afterChange(
                refused(
                    "account.username.change_too_soon",
                    details = mapOf("next_change_at" to "2026-12-14T10:00:00Z"),
                ),
                form,
            )

        assertEquals(
            UsernameUiState.Editing(
                current = "nadia_k",
                bannerKey = "account.username.change_too_soon",
                bannerDate = "2026-12-14T10:00:00Z",
            ),
            state,
        )
    }

    @Test
    fun `too soon without a date is the plain banner`() {
        val state = UsernameStateMapper.afterChange(refused("account.username.change_too_soon"), form)

        assertEquals(
            UsernameUiState.Editing(current = "nadia_k", bannerKey = "account.username.change_too_soon"),
            state,
        )
    }

    @Test
    fun `no password yet offers setting one`() {
        val state =
            UsernameStateMapper.afterChange(refused("account.username.password_required"), form)
                as UsernameUiState.Editing

        assertEquals(true, state.offerSetPassword)
        assertEquals("account.username.password_required", state.bannerKey)
    }

    @Test
    fun `a wrong current password goes under the password`() {
        val state =
            UsernameStateMapper.afterChange(refused("auth.password.current_wrong"), form) as UsernameUiState.Editing

        assertEquals("auth.password.current_wrong", state.passwordKey)
        assertEquals(null, state.bannerKey)
    }

    @Test
    fun `an unavailable or malformed name goes under the name`() {
        listOf("account.username.unavailable", "account.username.too_long").forEach { key ->
            val state = UsernameStateMapper.afterChange(refused(key), form) as UsernameUiState.Editing
            assertEquals(key, state.usernameKey)
        }
    }

    @Test
    fun `a 503 and no answer are retryable banners, too many attempts is not`() {
        val busy =
            UsernameStateMapper.afterChange(refused("error.temporarily_unavailable", retryable = true), form)
                as UsernameUiState.Editing
        val offline = UsernameStateMapper.afterChange(AuthResult.TransportFailure, form) as UsernameUiState.Editing
        val locked =
            UsernameStateMapper.afterChange(refused("auth.password.too_many_attempts"), form) as UsernameUiState.Editing

        assertEquals(true, busy.retryable)
        assertEquals(UsernameStateMapper.OFFLINE_KEY, offline.bannerKey)
        assertEquals(true, offline.retryable)
        assertEquals(false, locked.retryable)
        assertEquals(false, offline.saving)
    }

    @Test
    fun `the account read opens on the stored name, or none`() {
        assertEquals(
            UsernameUiState.Viewing("Nadia_K"),
            UsernameStateMapper.afterLoad(AuthResult.Ok(MeDto(username = "Nadia_K"))),
        )
        assertEquals(UsernameUiState.Viewing(null), UsernameStateMapper.afterLoad(AuthResult.TransportFailure))
    }

    @Test
    fun `no state prints the name`() {
        listOf(
            UsernameUiState.Viewing("sentinel_user_7"),
            UsernameUiState.Editing("sentinel_user_7"),
            UsernameUiState.Changed("sentinel_user_7", null),
        ).forEach { assertFalse("sentinel_user_7" in it.toString(), it.toString()) }
    }
}
