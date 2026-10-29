package com.shikkhokplus.app.feature.guardian

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.GuardianHomeDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/**
 * The guardian home's mapping: children, what to pay, how results moved,
 * and that switching replaces rather than stacks [BR4.2].
 */
class GuardianStateMapperTest {

    @Test
    fun `children carry the server's payment, waiting, trend and next class`() {
        val loaded =
            assertIs<GuardianUiState.Loaded>(
                GuardianStateMapper.afterLoad(GuardianHomeDto(listOf(childDto("Tasnim"))), null),
            )

        val child = loaded.child
        assertEquals("Tasnim", child.name)
        val payment = child.payment
        assertEquals(Money.of("1000.00"), payment?.option?.amountDue)
        assertEquals(Money.of("2000.00"), payment?.totalDue)
        assertEquals(1 to 37, payment?.let { it.laterPeriods to it.daysLate })
        assertEquals("Nagad", child.waiting.single().channel)
        assertEquals(Trend.UP to 39, child.results.single().let { it.trend to it.previousMarks })
        assertEquals("16:00", child.batches.single().next?.startTime)
    }

    @Test
    fun `no children is Empty with the guardian's number`() {
        assertEquals(
            GuardianUiState.Empty("+8801819552041"),
            GuardianStateMapper.afterLoad(GuardianHomeDto(), "+8801819552041"),
        )
    }

    @Test
    fun `switching child REPLACES the shown child and says so`() {
        val loaded =
            GuardianStateMapper.afterLoad(GuardianHomeDto(listOf(childDto("Tasnim"), childDto("Ayan"))), null)
                as GuardianUiState.Loaded

        val switched = GuardianStateMapper.select(loaded, 1)

        assertEquals("Ayan", switched.child.name)
        assertEquals(true, switched.switched)
        assertEquals(switched, GuardianStateMapper.select(switched, 1), "selecting the shown child changes nothing")
        assertEquals(
            switched,
            GuardianStateMapper.select(switched, 7),
            "an index the guardian does not reach is refused",
        )
    }

    @Test
    fun `an unknown trend reads as a first test, never as a direction`() {
        val dto =
            childDto("Tasnim").let { it.copy(latestResults = it.latestResults.map { r -> r.copy(trend = "sideways") }) }

        val loaded = GuardianStateMapper.afterLoad(GuardianHomeDto(listOf(dto)), null) as GuardianUiState.Loaded

        assertEquals(Trend.FIRST, loaded.child.results.single().trend)
    }

    @Test
    fun `failures carry the server's key, and offline is retryable`() {
        val envelope = ErrorEnvelope(ErrorBody("X", false, "error.not_available"))

        assertEquals(GuardianUiState.Failed("error.not_available", false), GuardianStateMapper.afterError(envelope))
        assertEquals(
            GuardianUiState.Failed(GuardianStateMapper.OFFLINE_KEY, true),
            GuardianStateMapper.afterTransportFailure(),
        )
    }
}
