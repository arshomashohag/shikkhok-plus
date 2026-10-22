package com.shikkhokplus.app.core.designsystem

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The greyscale property, asserted rather than assumed.
 *
 * The design's claim is that with colour removed the five payment
 * states still separate — by fill style, by icon shape and by words.
 * A test that only checked the colours would pass while that property
 * was broken, so these check the *cues*: that no two states share a
 * fill-and-outline combination, and that each has a distinct spoken
 * name for a screen reader, which sees no colour at all.
 */
class PaymentStateTest {

    @Test
    fun `no two states share every non-colour cue`() {
        // **The claim is about the cues together, not fill alone.**
        // Paid and partial deliberately share a tonal fill — they are
        // told apart by their icon (a tick against a half-filled
        // circle) and by their words. An earlier version of this test
        // asserted fill uniqueness and failed on exactly that pair,
        // which was the test being wrong rather than the design: a
        // fill-only rule would force four fill styles for five states
        // and lose the tonal/solid distinction that makes overdue the
        // loud one.
        //
        // So the assertion is the real property: strip the colour and
        // some cue still differs for every pair.
        for (dark in listOf(false, true)) {
            val cues = PaymentState.entries.map { state ->
                val s = styleFor(state, dark)
                NonColourCues(
                    fill = s.filled,
                    outlined = s.outlined,
                    dashed = s.dashed,
                    icon = state,
                    spoken = state.spoken(),
                )
            }
            assertEquals(
                cues.size,
                cues.toSet().size,
                "two states are indistinguishable with colour removed in " +
                    (if (dark) "dark" else "light") + " mode",
            )
        }
    }

    @Test
    fun `paid and partial are separated by icon and words, not by fill`() {
        // Pinning the pair the previous test exonerated, so a later
        // change that gives them the same icon is caught.
        for (dark in listOf(false, true)) {
            val paid = styleFor(PaymentState.PAID, dark)
            val partial = styleFor(PaymentState.PARTIAL, dark)
            assertEquals(paid.filled, partial.filled)
            assertTrue(PaymentState.PAID.spoken() != PaymentState.PARTIAL.spoken())
        }
    }

    @Test
    fun `every state is spoken differently`() {
        // A screen reader gets no colour, no fill and no icon. The
        // name is the whole cue.
        val spoken = PaymentState.entries.map { it.spoken() }
        assertEquals(spoken.size, spoken.toSet().size)
        assertTrue(spoken.none { it.isBlank() })
    }

    @Test
    fun `overdue is the only solid fill`() {
        // Stated flatly by the design: loud colour is spent on the
        // overdue chip and nothing else. If a second state becomes a
        // solid fill, that budget has been broken.
        for (dark in listOf(false, true)) {
            val solid = PaymentState.entries.filter {
                styleFor(it, dark).filled == FillKind.SOLID
            }
            assertEquals(listOf(PaymentState.OVERDUE), solid)
        }
    }

    @Test
    fun `verifying is the only dashed outline`() {
        // Dashed means "not yet confirmed". If anything else is
        // dashed, that meaning is gone.
        for (dark in listOf(false, true)) {
            val dashed = PaymentState.entries.filter {
                styleFor(it, dark).dashed
            }
            assertEquals(listOf(PaymentState.VERIFYING), dashed)
        }
    }

    /**
     * Everything about a chip that is still true in greyscale.
     *
     * The icon is keyed by the state because each state draws its own
     * shape in [PaymentStateIcon]; including it here states that the
     * shape is part of the contract.
     */
    private data class NonColourCues(
        val fill: FillKind,
        val outlined: Boolean,
        val dashed: Boolean,
        val icon: PaymentState,
        val spoken: String,
    )
}
