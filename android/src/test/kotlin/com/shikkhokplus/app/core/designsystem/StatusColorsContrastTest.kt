package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.ColorScheme
import androidx.compose.ui.graphics.Color
import kotlin.math.pow
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Every status colour pair, measured in both themes.
 *
 * **Computed, not asserted.** The palette's rule is 7:1 for text and
 * 3:1 for borders and swatches, and the first dark-theme defects this
 * file exists for were all literals someone believed met it: Today's
 * "short" ink was 1.86:1 on the dark card. So the ratio is calculated
 * from the WCAG 2 relative-luminance formula here, against the real
 * token objects, rather than copied from a comment.
 */
class StatusColorsContrastTest {

    private data class Check(val name: String, val ink: Color, val ground: Color, val floor: Double)

    private fun pairs(status: StatusColors, scheme: ColorScheme): List<Check> = listOf(
        Check("onPaidContainer on paidContainer", status.onPaidContainer, status.paidContainer, TEXT),
        Check("onSuccessFill on successFill", status.onSuccessFill, status.successFill, TEXT),
        Check("onPartialContainer on partialContainer", status.onPartialContainer, status.partialContainer, TEXT),
        Check("partialInk on surface", status.partialInk, scheme.surface, TEXT),
        Check("onDueContainer on dueContainer", status.onDueContainer, status.dueContainer, TEXT),
        Check("onOverdueFill on overdueFill", status.onOverdueFill, status.overdueFill, TEXT),
        Check(
            "onVerifyingContainer on verifyingContainer",
            status.onVerifyingContainer,
            status.verifyingContainer,
            TEXT,
        ),
        Check("heroCaption on primary", status.heroCaption, scheme.primary, TEXT),
        Check("onSurface on successTint", scheme.onSurface, status.successTint, TEXT),
        Check("onSurface on errorTint", scheme.onSurface, status.errorTint, TEXT),
        Check("inverseOnSurface on inverseSurface", scheme.inverseOnSurface, scheme.inverseSurface, TEXT),
        Check("dueOutline on surface", status.dueOutline, scheme.surface, NON_TEXT),
        Check("verifyingOutline on surface", status.verifyingOutline, scheme.surface, NON_TEXT),
        Check("successInk on surface", status.successInk, scheme.surface, NON_TEXT),
        Check("lateSwatch on surface", status.lateSwatch, scheme.surface, NON_TEXT),
        Check("inverseSurface notice on background", scheme.inverseSurface, scheme.background, NON_TEXT),
    )

    @Test
    fun `every light status pair meets its floor`() = assertFloors("light", LightStatusColors, ShikkhokLightColors)

    @Test
    fun `every dark status pair meets its floor`() = assertFloors("dark", DarkStatusColors, ShikkhokDarkColors)

    @Test
    fun `the formula reproduces the published black on white ratio`() {
        // A check on the checker: 21:1 is the WCAG maximum, by definition.
        assertEquals(21.0, contrast(Color.Black, Color.White), 0.01)
    }

    @Test
    fun `the formula catches the defect this file was written for`() {
        // #663C00 on the dark card: the old light-only "short" ink.
        assertTrue(contrast(Color(0xFF663C00), ShikkhokDarkColors.surface) < 2.0)
    }

    private fun assertFloors(theme: String, status: StatusColors, scheme: ColorScheme) {
        val failures =
            pairs(status, scheme).mapNotNull { pair ->
                val ratio = contrast(pair.ink, pair.ground)
                if (ratio < pair.floor) "${pair.name}: %.2f:1, needs %.1f:1".format(ratio, pair.floor) else null
            }
        assertTrue(failures.isEmpty(), "$theme theme pairs below their floor:\n" + failures.joinToString("\n"))
    }

    private fun contrast(a: Color, b: Color): Double {
        val la = relativeLuminance(a)
        val lb = relativeLuminance(b)
        return (maxOf(la, lb) + OFFSET) / (minOf(la, lb) + OFFSET)
    }

    private fun relativeLuminance(c: Color): Double =
        R_WEIGHT * linear(c.red) + G_WEIGHT * linear(c.green) + B_WEIGHT * linear(c.blue)

    private fun linear(channel: Float): Double {
        val v = channel.toDouble()
        return if (v <= KNEE) v / LINEAR_DIVISOR else ((v + GAMMA_OFFSET) / GAMMA_DIVISOR).pow(GAMMA)
    }

    private companion object {
        /** The palette's own text floor, stricter than AA's 4.5:1 (see Color.kt). */
        const val TEXT = 7.0

        /** WCAG 1.4.11: borders, swatches and other meaningful graphics. */
        const val NON_TEXT = 3.0

        const val OFFSET = 0.05
        const val R_WEIGHT = 0.2126
        const val G_WEIGHT = 0.7152
        const val B_WEIGHT = 0.0722
        const val KNEE = 0.04045
        const val LINEAR_DIVISOR = 12.92
        const val GAMMA_OFFSET = 0.055
        const val GAMMA_DIVISOR = 1.055
        const val GAMMA = 2.4
    }
}
