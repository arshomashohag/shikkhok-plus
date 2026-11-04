package com.shikkhokplus.app.core.designsystem

import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.junit4.createComposeRule
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertSame

/**
 * The theme hands out the status set that matches its own switch.
 *
 * The call sites used to work this out for themselves from the
 * surface's luminance, five times over. Now [ShikkhokTheme] decides
 * once; this pins that a screen forced dark gets the dark set even
 * when the system is light, which is the case a luminance guess was
 * standing in for.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class StatusColorsThemeTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `a forced dark theme provides the dark status colours`() {
        var seen: StatusColors? = null
        compose.setContent { ShikkhokTheme(darkTheme = true) { seen = MaterialTheme.statusColors } }
        compose.waitForIdle()
        assertSame(DarkStatusColors, seen)
    }

    @Test
    fun `a forced light theme provides the light status colours`() {
        var seen: StatusColors? = null
        compose.setContent { ShikkhokTheme(darkTheme = false) { seen = MaterialTheme.statusColors } }
        compose.waitForIdle()
        assertSame(LightStatusColors, seen)
    }
}
