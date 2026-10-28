package com.shikkhokplus.app.feature.inbox

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.InboxDto
import com.shikkhokplus.app.core.network.NotificationDto
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

/**
 * The inbox's mapping and its read-marking, as plain JVM tests so the
 * coverage report sees them.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class InboxViewModelTest {

    private val dispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setUp() {
        Dispatchers.setMain(dispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun message(
        id: String,
        kind: String = "fee_reminder",
        read: Boolean = false,
        period: String? = "2026-10",
    ) = NotificationDto(
        notificationId = id,
        kind = kind,
        batchName = "Physics",
        period = period,
        amount = Money.of("1200.00"),
        createdAt = "2026-10-17T06:00:00Z",
        read = read,
    )

    private class FakeRepository(
        var result: AuthResult<InboxDto>,
    ) : InboxRepository {
        var marked = 0

        override suspend fun inbox(): AuthResult<InboxDto> = result

        override suspend fun markRead(): AuthResult<Unit> {
            marked++
            return AuthResult.Ok(Unit)
        }
    }

    @Test
    fun `messages arrive in the server's order with its unread count`() = runTest(dispatcher) {
        val repo = FakeRepository(AuthResult.Ok(InboxDto(listOf(message("n-2"), message("n-1", read = true)), 1)))
        val model = InboxViewModel(repo)

        model.load()
        advanceUntilIdle()

        val loaded = assertIs<InboxUiState.Loaded>(model.state.value)
        assertEquals(listOf("n-2", "n-1"), loaded.messages.map { it.id })
        assertEquals(listOf(true, false), loaded.messages.map { it.unread })
        assertEquals(1, loaded.unread)
        assertEquals(Money.of("1200.00"), loaded.messages.first().amount)
        assertEquals(0, repo.marked, "the bell's read must not mark anything read")
    }

    @Test
    fun `a kind this version does not know is left out`() {
        val loaded =
            assertIs<InboxUiState.Loaded>(
                InboxMapper.afterLoad(InboxDto(listOf(message("n-1"), message("n-2", kind = "future")), 2)),
            )

        assertEquals(listOf("n-1"), loaded.messages.map { it.id })
        assertEquals(2, loaded.unread)
    }

    @Test
    fun `opening the inbox marks it read once it has shown unread messages`() = runTest(dispatcher) {
        val repo = FakeRepository(AuthResult.Ok(InboxDto(listOf(message("n-1")), 1)))
        val model = InboxViewModel(repo)

        model.open()
        advanceUntilIdle()

        assertEquals(1, repo.marked)
        assertEquals(true, assertIs<InboxUiState.Loaded>(model.state.value).messages.single().unread)
    }

    @Test
    fun `opening an inbox with nothing unread marks nothing`() = runTest(dispatcher) {
        val repo = FakeRepository(AuthResult.Ok(InboxDto(listOf(message("n-1", read = true)), 0)))
        val model = InboxViewModel(repo)

        model.open()
        advanceUntilIdle()

        assertEquals(0, repo.marked)
    }

    @Test
    fun `failures carry the server's key, and offline is retryable`() = runTest(dispatcher) {
        val refused =
            FakeRepository(
                AuthResult.Refused(
                    ErrorEnvelope(ErrorBody(code = "X", messageKey = "auth.expired", retryable = false)),
                ),
            )
        val offline = FakeRepository(AuthResult.TransportFailure)
        val refusedModel = InboxViewModel(refused)
        val offlineModel = InboxViewModel(offline)

        refusedModel.open()
        offlineModel.open()
        advanceUntilIdle()

        assertEquals(InboxUiState.Failed("auth.expired", false), refusedModel.state.value)
        assertEquals(InboxUiState.Failed(InboxMapper.OFFLINE_KEY, true), offlineModel.state.value)
        assertEquals(0, refused.marked + offline.marked)
    }
}
