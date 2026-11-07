package com.shikkhokplus.app.feature.payroll

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.AdjustmentBodyDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.SalaryAdjustmentDto
import com.shikkhokplus.app.core.network.SalaryLineDto
import com.shikkhokplus.app.core.network.SalaryPaymentBodyDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.myexams.Loadable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** A centre's payroll: draw, adjust, approve and pay; and My pay. */
@OptIn(ExperimentalCoroutinesApi::class)
class PayrollViewModelsTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun line(id: String, status: String = "draft", remaining: String = "10000.00") =
        SalaryLineDto(
            lineId = id,
            staffId = "s-$id",
            staffName = "Karim",
            centreName = "Alo Coaching",
            period = "2026-10",
            basis = "monthly",
            rate = Money.of("10000.00"),
            base = Money.of("10000.00"),
            owed = Money.of("10000.00"),
            paid = Money.of("0.00"),
            remaining = Money.of(remaining),
            status = status,
        )

    private inner class Fake : PayrollRepository {
        var lines = listOf(line("l-1"), line("l-2", status = "approved"))
        var lineResult: AuthResult<SalaryLineDto>? = null
        val periods = mutableListOf<String>()
        val drawn = mutableListOf<String>()
        val adjusted = mutableListOf<Pair<String, AdjustmentBodyDto>>()
        val paid = mutableListOf<Pair<String, SalaryPaymentBodyDto>>()
        val approved = mutableListOf<String>()
        val removed = mutableListOf<Pair<String, String>>()

        override suspend fun month(period: String): AuthResult<List<SalaryLineDto>> {
            periods += period
            return AuthResult.Ok(lines)
        }

        override suspend fun draw(period: String): AuthResult<List<SalaryLineDto>> {
            drawn += period
            return AuthResult.Ok(lines + line("l-3"))
        }

        override suspend fun adjust(lineId: String, body: AdjustmentBodyDto): AuthResult<SalaryLineDto> {
            adjusted += lineId to body
            return lineResult ?: AuthResult.Ok(
                line(lineId).copy(adjustments = listOf(SalaryAdjustmentDto("a-1", body.kind, body.label, body.amount))),
            )
        }

        override suspend fun removeAdjustment(lineId: String, adjustmentId: String): AuthResult<SalaryLineDto> {
            removed += lineId to adjustmentId
            return AuthResult.Ok(line(lineId))
        }

        override suspend fun approve(lineId: String): AuthResult<SalaryLineDto> {
            approved += lineId
            return lineResult ?: AuthResult.Ok(line(lineId, status = "approved"))
        }

        override suspend fun pay(lineId: String, body: SalaryPaymentBodyDto): AuthResult<SalaryLineDto> {
            paid += lineId to body
            return lineResult ?: AuthResult.Ok(line(lineId, status = "approved", remaining = "0.00"))
        }

        override suspend fun myPay(): AuthResult<List<SalaryLineDto>> = AuthResult.Ok(listOf(line("l-2", "approved")))
    }

    private fun keys(): () -> String {
        var n = 0
        return { "k-${++n}" }
    }

    private fun lines(model: PayrollViewModel) =
        assertIs<Loadable.Loaded<List<SalaryLineDto>>>(model.state.value.lines).value

    @Test
    fun `a month is read, and the month after the current one is never shown`() = runTest(dispatcher) {
        val fake = Fake()
        val model = PayrollViewModel(fake, month = "2026-10", newMutationId = keys())
        model.load()
        advanceUntilIdle()
        model.shift(-1)
        advanceUntilIdle()

        assertEquals(listOf("2026-10", "2026-09"), fake.periods)
        assertEquals(listOf("l-1", "l-2"), lines(model).map { it.lineId })
    }

    @Test
    fun `drawing the month replaces the list with the server's`() = runTest(dispatcher) {
        val fake = Fake()
        val model = PayrollViewModel(fake, month = "2026-10", newMutationId = keys())
        model.load()
        advanceUntilIdle()

        model.draw()
        advanceUntilIdle()

        assertEquals(listOf("2026-10"), fake.drawn)
        assertEquals(listOf("l-1", "l-2", "l-3"), lines(model).map { it.lineId })
        assertTrue(model.state.value.saved)
    }

    @Test
    fun `a deduction is sent with its trimmed label and typed amount, and the line is replaced`() =
        runTest(dispatcher) {
            val fake = Fake()
            val model = PayrollViewModel(fake, month = "2026-10", newMutationId = keys())
            model.load()
            advanceUntilIdle()

            model.openAdjust("l-1")
            model.adjustment(kind = DEDUCTION, label = "  Late  ", amount = "৫০০")
            model.submit()
            advanceUntilIdle()

            assertEquals(listOf("l-1" to AdjustmentBodyDto(DEDUCTION, "Late", Money.of("500.00"))), fake.adjusted)
            assertNull(model.state.value.sheet)
            assertEquals(1, lines(model).first { it.lineId == "l-1" }.adjustments.size)
        }

    @Test
    fun `an adjustment with no label or a zero amount is not sent`() = runTest(dispatcher) {
        val fake = Fake()
        val model = PayrollViewModel(fake, month = "2026-10", newMutationId = keys())
        model.load()
        advanceUntilIdle()

        model.openAdjust("l-1")
        model.adjustment(label = "Bonus", amount = "0")
        model.submit()
        model.adjustment(label = " ", amount = "100")
        model.submit()
        advanceUntilIdle()

        assertTrue(fake.adjusted.isEmpty())
    }

    @Test
    fun `a payment starts at what is left, and a refusal keeps the sheet and its replay key`() =
        runTest(dispatcher) {
            val fake = Fake()
            val model = PayrollViewModel(fake, month = "2026-10", newMutationId = keys())
            model.load()
            advanceUntilIdle()

            model.openPay("l-2")
            assertEquals("10000.00", (model.state.value.sheet as PayrollSheet.Pay).amount)
            fake.lineResult = AuthResult.Refused(ErrorEnvelope(ErrorBody("X", false, "payroll.overpaid")))
            model.payment(amount = "12000", note = " cash ")
            model.submit()
            advanceUntilIdle()
            assertEquals("payroll.overpaid", model.state.value.failureKey)

            fake.lineResult = null
            model.payment(amount = "10000")
            model.submit()
            advanceUntilIdle()

            assertEquals(listOf("k-1", "k-1"), fake.paid.map { it.second.clientMutationId })
            assertEquals("cash", fake.paid.last().second.note)
            assertNull(fake.paid.last().second.paidOn)
            assertNull(model.state.value.sheet)
            assertEquals("0.00", lines(model).first { it.lineId == "l-2" }.remaining.toString())
        }

    @Test
    fun `approving and removing an adjustment send the line's ids`() = runTest(dispatcher) {
        val fake = Fake()
        val model = PayrollViewModel(fake, month = "2026-10", newMutationId = keys())
        model.load()
        advanceUntilIdle()

        model.approve("l-1")
        advanceUntilIdle()
        model.removeAdjustment("l-1", "a-1")
        advanceUntilIdle()

        assertEquals(listOf("l-1"), fake.approved)
        assertEquals(listOf("l-1" to "a-1"), fake.removed)
    }

    @Test
    fun `my pay reads my own lines`() = runTest(dispatcher) {
        val model = MyPayViewModel(Fake())
        model.load()
        advanceUntilIdle()

        val loaded = assertIs<Loadable.Loaded<List<SalaryLineDto>>>(model.state.value)
        assertEquals(listOf("l-2"), loaded.value.map { it.lineId })
    }
}
