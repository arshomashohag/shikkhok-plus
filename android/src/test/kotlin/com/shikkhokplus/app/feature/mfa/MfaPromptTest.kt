package com.shikkhokplus.app.feature.mfa

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MfaRecoveryCodesDto
import com.shikkhokplus.app.core.network.MfaSetupDto
import com.shikkhokplus.app.core.network.MfaStatusDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.test.runTest
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The one-time offer after signing in, where its answer is kept, and the
 * mapping decisions the status page and the offer share [0028].
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MfaPromptTest {

    private fun dto(enabled: Boolean = false, recommended: Boolean = true, required: Boolean = false, left: Int = 0) =
        MfaStatusDto(enabled, null, left, recommended, required)

    /** A server that answers the status read with whatever is set. */
    private class StatusOnly(var result: AuthResult<MfaStatusDto>) : MfaRepository {
        var reads = 0

        override suspend fun status(): AuthResult<MfaStatusDto> {
            reads++
            return result
        }

        override suspend fun setup(): AuthResult<MfaSetupDto> = AuthResult.TransportFailure

        override suspend fun confirm(code: String): AuthResult<MfaRecoveryCodesDto> = AuthResult.TransportFailure

        override suspend fun disable(code: String?, recoveryCode: String?): AuthResult<MfaStatusDto> =
            AuthResult.TransportFailure

        override suspend fun renewRecoveryCodes(code: String): AuthResult<MfaRecoveryCodesDto> =
            AuthResult.TransportFailure
    }

    private fun prompt(
        result: AuthResult<MfaStatusDto>,
        store: MfaPromptStore = InMemoryMfaPromptStore(),
        holder: MfaStatusHolder = MfaStatusHolder(),
        account: String? = "acct-1",
    ) = MfaPrompt(StatusOnly(result), store, holder, { account })

    // ----- The offer ----------------------------------------------------

    @Test
    fun `a recommended account with it off is offered it, and the status is shared`() = runTest {
        val holder = MfaStatusHolder()

        assertTrue(prompt(AuthResult.Ok(dto()), holder = holder).check())
        assertEquals(true, holder.state.value?.showRecommended)
    }

    @Test
    fun `a student or guardian is never offered it`() = runTest {
        // The server does not recommend it for them; they find it in More.
        assertFalse(prompt(AuthResult.Ok(dto(recommended = false))).check())
    }

    @Test
    fun `an account that already has it on is not offered it`() = runTest {
        assertFalse(prompt(AuthResult.Ok(dto(enabled = true, left = 10))).check())
    }

    @Test
    fun `answering either way is remembered for that account only`() = runTest {
        val store = InMemoryMfaPromptStore()
        val first = prompt(AuthResult.Ok(dto()), store)
        assertTrue(first.check())

        first.answer()

        assertFalse(prompt(AuthResult.Ok(dto()), store).check())
        assertTrue(prompt(AuthResult.Ok(dto()), store, account = "acct-2").check())
    }

    @Test
    fun `an account the phone cannot name is not offered it, and nothing is remembered`() = runTest {
        val store = InMemoryMfaPromptStore()
        val nameless = prompt(AuthResult.Ok(dto()), store, account = null)

        assertFalse(nameless.check())
        nameless.answer()
        assertTrue(prompt(AuthResult.Ok(dto()), store).check())
    }

    @Test
    fun `a failed read offers nothing and says nothing`() = runTest {
        val holder = MfaStatusHolder()
        val refused =
            AuthResult.Refused(ErrorEnvelope(ErrorBody(code = "X", retryable = true, messageKey = "error.unexpected")))

        assertFalse(prompt(AuthResult.TransportFailure, holder = holder).check())
        assertFalse(prompt(refused, holder = holder).check())
        assertNull(holder.state.value)
    }

    @Test
    fun `answers survive a restart, per account`() {
        val preferences =
            ApplicationProvider.getApplicationContext<Context>()
                .getSharedPreferences("mfa-offer-test", Context.MODE_PRIVATE)
        preferences.edit().clear().commit()

        PreferencesMfaPromptStore(preferences).markSeen("acct-1")

        val reopened = PreferencesMfaPromptStore(preferences)
        assertTrue(reopened.seen("acct-1"))
        assertFalse(reopened.seen("acct-2"))
    }

    // ----- The mapping --------------------------------------------------

    @Test
    fun `recommended is drawn only while it is off`() {
        assertTrue(MfaMapper.statusOf(dto()).showRecommended)
        assertFalse(MfaMapper.statusOf(dto(enabled = true, left = 10)).showRecommended)
        assertFalse(MfaMapper.statusOf(dto(recommended = false)).showRecommended)
    }

    @Test
    fun `required hides Turn off`() {
        val admin = MfaMapper.statusOf(dto(enabled = true, required = true, left = 10))

        assertTrue(admin.required)
        assertFalse(admin.canTurnOff)
        assertTrue(MfaMapper.statusOf(dto(enabled = true, left = 10)).canTurnOff)
        assertFalse(MfaMapper.statusOf(dto()).canTurnOff, "nothing to turn off while it is off")
    }

    @Test
    fun `the few-codes warning starts at two and needs it on`() {
        assertTrue(MfaMapper.statusOf(dto(enabled = true, left = 2)).lowOnCodes)
        assertTrue(MfaMapper.statusOf(dto(enabled = true, left = 0)).lowOnCodes)
        assertFalse(MfaMapper.statusOf(dto(enabled = true, left = 3)).lowOnCodes)
        assertFalse(MfaMapper.statusOf(dto(enabled = false, left = 0)).lowOnCodes)
    }

    @Test
    fun `the secret is shown in fours, whatever spacing it came with`() {
        assertEquals("JBSW Y3DP EHPK 3PXP", MfaMapper.groupSecret("JBSWY3DPEHPK3PXP"))
        assertEquals("ABCD EF", MfaMapper.groupSecret("AB CD EF"))
        assertEquals("", MfaMapper.groupSecret(""))
    }

    @Test
    fun `a failed write carries the server's key, or the offline key when nothing answered`() {
        val refused =
            AuthResult.Refused(ErrorEnvelope(ErrorBody(code = "X", retryable = false, messageKey = "mfa.locked")))

        assertEquals(WriteState.Failed("mfa.locked", false), MfaMapper.failure(refused))
        assertEquals(WriteState.Failed(MfaMapper.OFFLINE_KEY, true), MfaMapper.failure(AuthResult.TransportFailure))
    }
}
