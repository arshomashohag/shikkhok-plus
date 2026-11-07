package com.shikkhokplus.app.feature.mfa

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.MfaRecoveryCodesDto
import com.shikkhokplus.app.core.network.MfaSetupDto
import com.shikkhokplus.app.core.network.MfaStatusDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * The two-step verification screen's state machine [0028]: the status
 * read, turning on, recovery codes, turning off and new codes, each with
 * its loading state, its refusals and its explicit retry.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class MfaViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private val off = MfaStatusDto(false, null, 0, recommended = true, required = false)
    private val on = MfaStatusDto(true, "2026-11-06T04:00:00Z", 10, recommended = true, required = false)
    private val tenCodes = MfaRecoveryCodesDto(List(10) { "CODE$it-XXXXX" })

    private fun refused(key: String, retryable: Boolean = false) =
        AuthResult.Refused(ErrorEnvelope(ErrorBody(code = "X", retryable = retryable, messageKey = key)))

    /** A server whose answers each test sets, recording what was sent. */
    private class FakeMfa : MfaRepository {
        var statusResult: AuthResult<MfaStatusDto> = AuthResult.TransportFailure
        var setupResult: AuthResult<MfaSetupDto> = AuthResult.TransportFailure
        var confirmResult: AuthResult<MfaRecoveryCodesDto> = AuthResult.TransportFailure
        var disableResult: AuthResult<MfaStatusDto> = AuthResult.TransportFailure
        var renewResult: AuthResult<MfaRecoveryCodesDto> = AuthResult.TransportFailure
        var statusReads = 0
        var setups = 0
        val confirms = mutableListOf<String>()
        val disables = mutableListOf<Pair<String?, String?>>()
        val renewals = mutableListOf<String>()

        override suspend fun status(): AuthResult<MfaStatusDto> {
            statusReads++
            return statusResult
        }

        override suspend fun setup(): AuthResult<MfaSetupDto> {
            setups++
            return setupResult
        }

        override suspend fun confirm(code: String): AuthResult<MfaRecoveryCodesDto> {
            confirms += code
            return confirmResult
        }

        override suspend fun disable(code: String?, recoveryCode: String?): AuthResult<MfaStatusDto> {
            disables += code to recoveryCode
            return disableResult
        }

        override suspend fun renewRecoveryCodes(code: String): AuthResult<MfaRecoveryCodesDto> {
            renewals += code
            return renewResult
        }
    }

    private fun TestScope.loaded(repo: FakeMfa, holder: MfaStatusHolder? = null): MfaViewModel {
        val model = MfaViewModel(repo, holder)
        model.load()
        advanceUntilIdle()
        return model
    }

    // ----- The status --------------------------------------------------

    @Test
    fun `the status starts loading, then shows what the server said and shares it`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { statusResult = AuthResult.Ok(off) }
        val holder = MfaStatusHolder()
        val model = MfaViewModel(repo, holder)
        assertEquals(MfaStatusUiState.Loading, model.state.value.status)

        model.load()
        advanceUntilIdle()

        val loaded = assertIs<MfaStatusUiState.Loaded>(model.state.value.status)
        assertTrue(loaded.status.showRecommended)
        assertEquals(loaded.status, holder.state.value)
    }

    @Test
    fun `a failed status read offers a retry, which shows the loader and reads again`() = runTest(dispatcher) {
        val repo = FakeMfa()
        val model = loaded(repo)
        assertEquals(MfaStatusUiState.Failed(MfaMapper.OFFLINE_KEY, retryable = true), model.state.value.status)

        repo.statusResult = AuthResult.Ok(on)
        model.retry()
        assertEquals(MfaStatusUiState.Loading, model.state.value.status)
        advanceUntilIdle()

        assertIs<MfaStatusUiState.Loaded>(model.state.value.status)
        assertEquals(2, repo.statusReads)
    }

    @Test
    fun `a refused status read carries the server's key and retryability`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { statusResult = refused("auth.token.not_valid") }

        val model = loaded(repo)

        assertEquals(MfaStatusUiState.Failed("auth.token.not_valid", retryable = false), model.state.value.status)
    }

    // ----- Turning on ---------------------------------------------------

    @Test
    fun `turning on asks for a secret, then shows it in fours with the link`() = runTest(dispatcher) {
        val repo =
            FakeMfa().apply {
                statusResult = AuthResult.Ok(off)
                setupResult = AuthResult.Ok(MfaSetupDto("JBSWY3DPEHPK3PXP", "otpauth://totp/x"))
            }
        val model = loaded(repo)

        model.turnOn()
        assertEquals(MfaFlow.Starting(WriteState.Saving), model.state.value.flow)
        advanceUntilIdle()

        val step = assertIs<MfaFlow.Confirming>(model.state.value.flow)
        assertEquals("JBSWY3DPEHPK3PXP", step.secret)
        assertEquals("JBSW Y3DP EHPK 3PXP", step.secretGroups)
        assertEquals("otpauth://totp/x", step.otpauthUri)
    }

    @Test
    fun `a failed start offers the retry, which asks again`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { statusResult = AuthResult.Ok(off) }
        val model = loaded(repo)

        model.turnOn()
        advanceUntilIdle()
        assertEquals(
            MfaFlow.Starting(WriteState.Failed(MfaMapper.OFFLINE_KEY, retryable = true)),
            model.state.value.flow,
        )
        assertEquals(1, repo.setups, "the failure must not auto-retry")

        repo.setupResult = AuthResult.Ok(MfaSetupDto("ABCDEFGH", "otpauth://totp/x"))
        model.turnOn()
        advanceUntilIdle()

        assertIs<MfaFlow.Confirming>(model.state.value.flow)
        assertEquals(2, repo.setups)
    }

    @Test
    fun `already on is the server's refusal, shown on the start step`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { setupResult = refused("mfa.already_enabled") }
        val model = loaded(repo)

        model.turnOn()
        advanceUntilIdle()

        assertEquals(MfaFlow.Starting(WriteState.Failed("mfa.already_enabled", false)), model.state.value.flow)
    }

    private fun TestScope.confirming(repo: FakeMfa, holder: MfaStatusHolder? = null): MfaViewModel {
        repo.setupResult = AuthResult.Ok(MfaSetupDto("JBSWY3DPEHPK3PXP", "otpauth://totp/x"))
        val model = loaded(repo, holder)
        model.turnOn()
        advanceUntilIdle()
        return model
    }

    @Test
    fun `the first code is sent only once it is six digits`() = runTest(dispatcher) {
        val repo = FakeMfa()
        val model = confirming(repo)

        model.type("12345")
        model.confirm()
        advanceUntilIdle()

        assertEquals(emptyList(), repo.confirms)
        assertFalse(assertIs<MfaFlow.Confirming>(model.state.value.flow).canSubmit)
    }

    @Test
    fun `a right first code shows the ten codes once and re-reads the status beneath`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { statusResult = AuthResult.Ok(off) }
        val holder = MfaStatusHolder()
        val model = confirming(repo, holder)
        repo.confirmResult = AuthResult.Ok(tenCodes)
        repo.statusResult = AuthResult.Ok(on.copy(recommended = true))

        model.type("123456")
        model.confirm()
        assertEquals(WriteState.Saving, assertIs<MfaFlow.Confirming>(model.state.value.flow).write)
        advanceUntilIdle()

        assertEquals(MfaFlow.Codes(tenCodes.recoveryCodes, renewed = false), model.state.value.flow)
        assertEquals(listOf("123456"), repo.confirms)
        val status = assertIs<MfaStatusUiState.Loaded>(model.state.value.status).status
        assertTrue(status.enabled)
        assertFalse(assertNotNull(holder.state.value).showRecommended, "More's mark goes once it is on")
    }

    @Test
    fun `a wrong first code keeps the step and the code, and typing clears the refusal`() = runTest(dispatcher) {
        val repo = FakeMfa()
        val model = confirming(repo)
        repo.confirmResult = refused("mfa.code_wrong")

        model.type("000000")
        model.confirm()
        advanceUntilIdle()

        val step = assertIs<MfaFlow.Confirming>(model.state.value.flow)
        assertEquals(WriteState.Failed("mfa.code_wrong", false), step.write)
        assertEquals("000000", step.code)

        model.type("")
        assertEquals(WriteState.Idle, assertIs<MfaFlow.Confirming>(model.state.value.flow).write)
    }

    @Test
    fun `no answer to the first code offers the retry, which sends the same code`() = runTest(dispatcher) {
        val repo = FakeMfa()
        val model = confirming(repo)

        model.type("123456")
        model.confirm()
        advanceUntilIdle()
        assertEquals(
            WriteState.Failed(MfaMapper.OFFLINE_KEY, retryable = true),
            assertIs<MfaFlow.Confirming>(model.state.value.flow).write,
        )
        assertEquals(1, repo.confirms.size, "the failure must not auto-retry")

        repo.confirmResult = AuthResult.Ok(tenCodes)
        model.confirm()
        advanceUntilIdle()

        assertEquals(listOf("123456", "123456"), repo.confirms)
        assertIs<MfaFlow.Codes>(model.state.value.flow)
    }

    @Test
    fun `no authenticator app on the phone is said on the step`() = runTest(dispatcher) {
        val model = confirming(FakeMfa())

        model.noAuthenticatorApp()

        assertTrue(assertIs<MfaFlow.Confirming>(model.state.value.flow).noAuthenticator)
    }

    @Test
    fun `saving the codes drops them, and cancel cannot`() = runTest(dispatcher) {
        val repo = FakeMfa()
        val model = confirming(repo)
        repo.confirmResult = AuthResult.Ok(tenCodes)
        model.type("123456")
        model.confirm()
        advanceUntilIdle()

        model.cancel()
        assertIs<MfaFlow.Codes>(model.state.value.flow)

        model.finishCodes()
        assertEquals(MfaFlow.None, model.state.value.flow)
    }

    @Test
    fun `an answer arriving after the step was left changes nothing`() = runTest(dispatcher) {
        val repo = FakeMfa()
        val model = confirming(repo)
        repo.confirmResult = refused("mfa.code_wrong")

        model.type("123456")
        model.confirm()
        model.cancel()
        advanceUntilIdle()

        assertEquals(MfaFlow.None, model.state.value.flow)
    }

    // ----- Turning off --------------------------------------------------

    @Test
    fun `turning off with an app code shows the new status at once and shares it`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { statusResult = AuthResult.Ok(on) }
        val holder = MfaStatusHolder()
        val model = loaded(repo, holder)
        repo.disableResult = AuthResult.Ok(off)

        model.startTurnOff()
        model.type("123456")
        model.turnOff()
        assertEquals(WriteState.Saving, assertIs<MfaFlow.TurningOff>(model.state.value.flow).write)
        advanceUntilIdle()

        assertEquals(listOf<Pair<String?, String?>>("123456" to null), repo.disables)
        assertEquals(MfaFlow.None, model.state.value.flow)
        assertFalse(assertIs<MfaStatusUiState.Loaded>(model.state.value.status).status.enabled)
        assertTrue(assertNotNull(holder.state.value).showRecommended)
    }

    @Test
    fun `turning off with a recovery code sends it trimmed, in its own field`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { statusResult = AuthResult.Ok(on) }
        val model = loaded(repo)
        repo.disableResult = AuthResult.Ok(off)

        model.startTurnOff()
        model.toggleRecoveryCode()
        model.type(" ABCDE-FGHJK ")
        model.turnOff()
        advanceUntilIdle()

        assertEquals(listOf<Pair<String?, String?>>(null to "ABCDE-FGHJK"), repo.disables)
    }

    @Test
    fun `switching the kind of code empties what was typed`() = runTest(dispatcher) {
        val model = loaded(FakeMfa())

        model.startTurnOff()
        model.type("123")
        model.toggleRecoveryCode()

        assertEquals(MfaFlow.TurningOff(useRecovery = true), model.state.value.flow)
    }

    @Test
    fun `a short recovery code is not sent`() = runTest(dispatcher) {
        val repo = FakeMfa()
        val model = loaded(repo)

        model.startTurnOff()
        model.toggleRecoveryCode()
        model.type("ABCDE")
        model.turnOff()
        advanceUntilIdle()

        assertEquals(emptyList(), repo.disables)
    }

    @Test
    fun `an administrator's refusal stays on the step with the server's words`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { disableResult = refused("mfa.required_for_admin") }
        val model = loaded(repo)

        model.startTurnOff()
        model.type("123456")
        model.turnOff()
        advanceUntilIdle()

        val step = assertIs<MfaFlow.TurningOff>(model.state.value.flow)
        assertEquals(WriteState.Failed("mfa.required_for_admin", false), step.write)
    }

    @Test
    fun `no answer to turning off offers the retry, which sends again`() = runTest(dispatcher) {
        val repo = FakeMfa()
        val model = loaded(repo)
        model.startTurnOff()
        model.type("123456")
        model.turnOff()
        advanceUntilIdle()
        assertEquals(1, repo.disables.size, "the failure must not auto-retry")

        repo.disableResult = AuthResult.Ok(off)
        model.turnOff()
        advanceUntilIdle()

        assertEquals(2, repo.disables.size)
        assertEquals(MfaFlow.None, model.state.value.flow)
    }

    @Test
    fun `cancel leaves turning off`() = runTest(dispatcher) {
        val model = loaded(FakeMfa())

        model.startTurnOff()
        model.cancel()

        assertEquals(MfaFlow.None, model.state.value.flow)
    }

    // ----- New recovery codes -------------------------------------------

    @Test
    fun `new codes are shown once, marked as replacing the old`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { statusResult = AuthResult.Ok(on.copy(recoveryCodesLeft = 1)) }
        val model = loaded(repo)
        repo.renewResult = AuthResult.Ok(tenCodes)
        repo.statusResult = AuthResult.Ok(on)

        model.startNewCodes()
        model.type("123456")
        model.renewCodes()
        assertEquals(WriteState.Saving, assertIs<MfaFlow.Renewing>(model.state.value.flow).write)
        advanceUntilIdle()

        assertEquals(MfaFlow.Codes(tenCodes.recoveryCodes, renewed = true), model.state.value.flow)
        assertEquals(listOf("123456"), repo.renewals)
        assertEquals(10, assertIs<MfaStatusUiState.Loaded>(model.state.value.status).status.recoveryCodesLeft)
    }

    @Test
    fun `no answer to new codes offers the retry, which sends the same code`() = runTest(dispatcher) {
        val repo = FakeMfa()
        val model = loaded(repo)
        model.startNewCodes()
        model.type("123456")
        model.renewCodes()
        advanceUntilIdle()
        assertEquals(
            WriteState.Failed(MfaMapper.OFFLINE_KEY, retryable = true),
            assertIs<MfaFlow.Renewing>(model.state.value.flow).write,
        )

        repo.renewResult = AuthResult.Ok(tenCodes)
        model.renewCodes()
        advanceUntilIdle()

        assertEquals(listOf("123456", "123456"), repo.renewals)
        assertIs<MfaFlow.Codes>(model.state.value.flow)
    }

    @Test
    fun `a wrong code for new codes is the server's refusal`() = runTest(dispatcher) {
        val repo = FakeMfa().apply { renewResult = refused("mfa.code_wrong") }
        val model = loaded(repo)

        model.startNewCodes()
        model.type("000000")
        model.renewCodes()
        advanceUntilIdle()

        assertEquals(
            WriteState.Failed("mfa.code_wrong", false),
            assertIs<MfaFlow.Renewing>(model.state.value.flow).write,
        )
    }

    @Test
    fun `typing with no step in progress changes nothing`() = runTest(dispatcher) {
        val model = loaded(FakeMfa())

        model.type("123456")
        model.confirm()
        model.turnOff()
        model.renewCodes()
        model.noAuthenticatorApp()
        model.finishCodes()

        assertEquals(MfaFlow.None, model.state.value.flow)
    }
}
