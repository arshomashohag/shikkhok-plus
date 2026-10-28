package com.shikkhokplus.app.feature.batchdetail

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.AnnouncementDto
import com.shikkhokplus.app.core.network.BatchDto
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.RosterFeeRowDto
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.auth.AuthResult
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

/**
 * T7's chips and notices. Each chip follows the server's fields in a
 * fixed order and compares no amount [TC-9].
 */
@OptIn(ExperimentalCoroutinesApi::class)
class BatchDetailViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() = Dispatchers.setMain(dispatcher)

    @AfterTest
    fun tearDown() = Dispatchers.resetMain()

    private fun row(
        status: String? = "unpaid",
        days: Int? = null,
        verifying: String? = null,
        outstanding: String = "1200.00",
    ) = RosterFeeRowDto(
        enrollmentId = "e-1",
        displayName = "Rahim",
        outstanding = Money.of(outstanding),
        currentPeriod = "2026-10",
        currentStatus = status,
        dueDate = "2026-10-20",
        daysOverdue = days,
        verifying = verifying?.let(Money::of),
    )

    @Test
    fun `a waiting payment outranks being late, which outranks the period's status`() {
        assertEquals(FeeChipKind.VERIFYING, BatchDetailMapper.chipFor(row(days = 68, verifying = "800.00"))?.kind)
        val late = BatchDetailMapper.chipFor(row(status = "partly_paid", days = 68, outstanding = "3600.00"))
        assertEquals(FeeChip(FeeChipKind.OVERDUE, Money.of("3600.00"), 68), late)
    }

    @Test
    fun `each period status gets its own chip`() {
        assertEquals(FeeChipKind.PARTIAL, BatchDetailMapper.chipFor(row(status = "partly_paid"))?.kind)
        assertEquals(FeeChipKind.PAID, BatchDetailMapper.chipFor(row(status = "paid"))?.kind)
        assertEquals(FeeChipKind.WAIVED, BatchDetailMapper.chipFor(row(status = "waived"))?.kind)
        assertEquals("2026-10-20", BatchDetailMapper.chipFor(row(status = "unpaid"))?.dueDate)
        assertNull(BatchDetailMapper.chipFor(row(status = null)))
    }

    private class Fake(
        var fees: AuthResult<List<RosterFeeRowDto>> = AuthResult.Ok(emptyList()),
        var write: AuthResult<Unit> = AuthResult.Ok(Unit),
    ) : BatchDetailRepository {
        val posted = mutableListOf<String>()
        val removed = mutableListOf<String>()
        var notices = listOf(AnnouncementDto("n-1", "Bring a calculator", "2026-10-26T09:00:00Z"))

        override suspend fun batch(batchId: String) =
            AuthResult.Ok(BatchDto(id = batchId, name = "Physics A", defaultFee = Money.of("1200.00"), feeDueDay = 10))

        override suspend fun fees(batchId: String) = fees

        override suspend fun notices(batchId: String): AuthResult<List<AnnouncementDto>> = AuthResult.Ok(notices)

        override suspend fun postNotice(batchId: String, body: String): AuthResult<Unit> {
            posted += body
            return write
        }

        override suspend fun editNotice(noticeId: String, body: String): AuthResult<Unit> = write

        override suspend fun removeNotice(noticeId: String): AuthResult<Unit> {
            removed += noticeId
            return write
        }
    }

    @Test
    fun `loading reads the header, chips and notices`() = runTest(dispatcher) {
        val model = BatchDetailViewModel(Fake())

        model.load("b-1")
        advanceUntilIdle()

        val state = model.state.value
        assertEquals("Physics A", state.header?.name)
        assertEquals(10, state.header?.feeDueDay)
        assertIs<FeeChips.Loaded>(state.fees)
        assertEquals("Bring a calculator", state.notices?.single()?.body)
    }

    @Test
    fun `fees that fail to load are hidden, and a retry reads them again`() = runTest(dispatcher) {
        val fake = Fake(fees = AuthResult.TransportFailure)
        val model = BatchDetailViewModel(fake)
        model.load("b-1")
        advanceUntilIdle()
        assertEquals(FeeChips.Failed, model.state.value.fees)

        fake.fees = AuthResult.Ok(emptyList())
        model.refreshFees()
        advanceUntilIdle()
        assertIs<FeeChips.Loaded>(model.state.value.fees)
    }

    @Test
    fun `a posted notice is trimmed and the list reloads`() = runTest(dispatcher) {
        val fake = Fake()
        val model = BatchDetailViewModel(fake)
        model.load("b-1")
        advanceUntilIdle()

        fake.notices = fake.notices + AnnouncementDto("n-2", "Test on Saturday", "2026-10-28T09:00:00Z")
        model.postNotice("  Test on Saturday  ")
        advanceUntilIdle()

        assertEquals(listOf("Test on Saturday"), fake.posted)
        assertEquals(WriteState.Saved, model.state.value.noticeWrite)
        assertEquals(2, model.state.value.notices?.size)
        model.acknowledgeNotice()
        assertEquals(WriteState.Idle, model.state.value.noticeWrite)
    }

    @Test
    fun `a refused notice write says why and changes nothing`() = runTest(dispatcher) {
        val refused = AuthResult.Refused(ErrorEnvelope(ErrorBody("BATCH_INACTIVE", false, "teaching.batch.inactive")))
        val fake = Fake(write = refused)
        val model = BatchDetailViewModel(fake)
        model.load("b-1")
        advanceUntilIdle()

        model.removeNotice("n-1")
        advanceUntilIdle()

        val failed = assertIs<WriteState.Failed>(model.state.value.noticeWrite)
        assertEquals("teaching.batch.inactive", failed.messageKey)
        assertEquals(listOf("n-1"), fake.removed)
    }

    @Test
    fun `tabs switch without reloading`() {
        val model = BatchDetailViewModel(Fake())

        model.select(BatchTab.NOTICES)

        assertEquals(BatchTab.NOTICES, model.state.value.tab)
    }
}
