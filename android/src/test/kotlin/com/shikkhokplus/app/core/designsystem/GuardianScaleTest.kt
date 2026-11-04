package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The guardian's larger scale (G1–G4) keeps the design's own rules.
 *
 * **Larger, never off the scale.** Each slot is the standard slot or one
 * of the seven steps above it, so the 13sp floor and the Bangla
 * line-height ratio hold by the same table TypographyScaleTest uses; and
 * no slot is smaller than the standard one, which would make a guardian
 * screen harder to read than a teacher's.
 */
class GuardianScaleTest {

    private fun slots(of: Typography): Map<String, TextStyle> =
        Typography::class.java.methods
            .filter { it.parameterCount == 0 && it.returnType == TextStyle::class.java }
            .associate { it.name.removePrefix("get") to it.invoke(of) as TextStyle }

    private val designSteps =
        mapOf(34f to 52f, 26f to 40f, 21f to 34f, 18f to 30f, 16f to 26f, 14f to 22f, 13f to 20f)

    @Test
    fun `every guardian style is one of the design's seven steps`() {
        val off = slots(GuardianTypography).filter { (_, s) -> designSteps[s.fontSize.value] != s.lineHeight.value }
        assertEquals(emptyMap(), off.mapValues { "${it.value.fontSize}/${it.value.lineHeight}" })
    }

    @Test
    fun `no guardian style is smaller than the standard one`() {
        val standard = slots(ShikkhokTypography)
        val smaller =
            slots(GuardianTypography).filter { (name, s) -> s.fontSize.value < standard.getValue(name).fontSize.value }
        assertEquals(emptyMap(), smaller.mapValues { it.value.fontSize })
    }

    @Test
    fun `the guardian's reach is at least the standard reach everywhere`() {
        assertTrue(GuardianTouch.touch >= StandardTouch.touch)
        assertTrue(GuardianTouch.moneyButton >= StandardTouch.moneyButton)
        assertTrue(GuardianTouch.rowSingle >= StandardTouch.rowSingle)
        assertTrue(GuardianTouch.compactChip >= StandardTouch.compactChip)
    }

    @Test
    fun `the guardian boards' sizes are the ones built`() {
        // G4: 60dp main buttons, 56dp others, 64dp rows, 30dp chips.
        assertEquals(60f, GuardianTouch.moneyButton.value)
        assertEquals(56f, GuardianTouch.touch.value)
        assertEquals(64f, GuardianTouch.rowSingle.value)
        assertEquals(30f, GuardianTouch.compactChip.value)
    }
}
