package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Every text style the app can reach sits on the design's scale.
 *
 * **The mechanism that replaces "obvious in review".** Four Material
 * slots were left at their defaults on the reasoning that using one
 * would be noticed. They were used throughout the screens and nobody
 * noticed, so text fell below the 13sp floor and under the line-height
 * ratio Bangla needs. This test fails instead.
 *
 * The rules are the design's own (TypeScale.dc.html): "caption 13/20 --
 * floor, nothing smaller", and "line height is at least 1.53x the size
 * on every step", because tighter ratios clip Bangla conjuncts.
 */
class TypographyScaleTest {

    /**
     * Every slot of M3's Typography, by name.
     *
     * Read by reflection over the getters so a slot added to Material in
     * a future release is checked too, rather than silently defaulting.
     */
    private fun allSlots(): Map<String, TextStyle> =
        Typography::class.java.methods
            .filter { it.parameterCount == 0 && it.returnType == TextStyle::class.java }
            .associate { it.name.removePrefix("get") to it.invoke(ShikkhokTypography) as TextStyle }

    private companion object {
        /** The tightest ratio on the design's scale, 34/52, rounded down. */
        const val MIN_RATIO: Float = 1.52f
    }

    /** The design's seven steps: size to line height, in sp. */
    private val designSteps =
        mapOf(34f to 52f, 26f to 40f, 21f to 34f, 18f to 30f, 16f to 26f, 14f to 22f, 13f to 20f)

    @Test
    fun `the reflection actually finds the slots`() {
        // Fifteen in Material 3 today. A reflection returning nothing
        // would make every test below pass vacuously.
        assertTrue(allSlots().size >= 15, "found only ${allSlots().keys}")
    }

    @Test
    fun `no style is smaller than the caption floor`() {
        val below = allSlots().filter { it.value.fontSize.value < 13f }
        assertEquals(emptyMap(), below.mapValues { it.value.fontSize }, "below 13sp")
    }

    @Test
    fun `every style keeps the Bangla line-height ratio`() {
        // **1.52, not the 1.53 the design states.** The design's own
        // display step is 34/52, a ratio of 1.529 -- its "at least
        // 1.53x" is that figure rounded. Testing the rounded description
        // would fail the design's own scale. The exact-step test below
        // pins every value precisely; this one catches a slot that
        // drifts off the scale in a direction that clips.
        val tight =
            allSlots().filter { (_, style) ->
                style.lineHeight.value / style.fontSize.value < MIN_RATIO
            }
        assertEquals(
            emptyMap(),
            tight.mapValues { "${it.value.fontSize}/${it.value.lineHeight}" },
            "under 1.53x clips Bangla conjuncts",
        )
    }

    @Test
    fun `every style is one of the design's seven steps`() {
        // Not merely above the floor: ON the scale. A 15sp slot would
        // pass both tests above and still be a size the design never
        // drew or checked against Bangla.
        val off =
            allSlots().filter { (_, style) ->
                designSteps[style.fontSize.value] != style.lineHeight.value
            }
        assertEquals(
            emptyMap(),
            off.mapValues { "${it.value.fontSize}/${it.value.lineHeight}" },
            "not a TypeScale.dc.html step",
        )
    }
}
