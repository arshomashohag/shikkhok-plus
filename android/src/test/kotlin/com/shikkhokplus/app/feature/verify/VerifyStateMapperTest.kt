package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.network.ReviewMethodDto
import com.shikkhokplus.app.core.network.VerificationQueueDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull

/** The destination snapshots the server really writes all map, none fails a list. */
class VerifyStateMapperTest {

    private fun method(dto: ReviewMethodDto) = assertNotNull(VerifyStateMapper.toCard(review(method = dto))).method

    @Test
    fun `a cash snapshot with no channel is cash in hand`() {
        assertEquals(MethodKind.CASH, method(ReviewMethodDto(kind = "cash")).kind)
    }

    @Test
    fun `a cash channel on any kind is still cash in hand`() {
        assertEquals(MethodKind.CASH, method(ReviewMethodDto(kind = "channel", channel = "cash")).kind)
    }

    @Test
    fun `a legacy snapshot shows its channel as the provider with no number`() {
        val legacy = method(ReviewMethodDto(kind = "legacy", channel = "Nagad"))

        assertEquals(MethodKind.OTHER, legacy.kind)
        assertEquals("Nagad", legacy.provider)
        assertNull(legacy.number)
    }

    @Test
    fun `an unknown kind degrades to a generic method`() {
        val other = method(ReviewMethodDto(kind = "crypto"))

        assertEquals(MethodKind.OTHER, other.kind)
        assertEquals("crypto", other.provider)
    }

    @Test
    fun `one odd destination does not break the rest of the queue`() {
        val queue =
            VerificationQueueDto(
                pending =
                    listOf(
                        review(id = "a"),
                        review(id = "b", method = ReviewMethodDto(kind = "legacy", channel = "Nagad")),
                        review(id = "c", method = ReviewMethodDto(kind = "cash")),
                    ),
            )

        val waiting = assertIs<VerifyUiState.Waiting>(VerifyStateMapper.afterLoad(queue))

        assertEquals(listOf("a", "b", "c"), waiting.pending.map { it.submissionId })
    }
}
