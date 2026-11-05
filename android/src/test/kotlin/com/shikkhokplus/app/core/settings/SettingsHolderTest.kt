package com.shikkhokplus.app.core.settings

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Settings: defaults, what a change keeps, and a value from the future. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class SettingsHolderTest {

    private fun preferences() =
        ApplicationProvider.getApplicationContext<Context>().getSharedPreferences("settings-test", Context.MODE_PRIVATE)

    @Test
    fun `nothing stored reads as the phone's own theme and size, with notifications on`() {
        preferences().edit().clear().commit()

        assertEquals(AppSettings(), PreferencesSettingsStore(preferences()).read())
    }

    @Test
    fun `a change is live at once and survives a restart`() {
        preferences().edit().clear().commit()
        val holder = SettingsHolder(PreferencesSettingsStore(preferences()))

        holder.update { it.copy(theme = ThemeChoice.DARK, textSize = TextSizeChoice.LARGEST, notifications = false) }

        assertEquals(ThemeChoice.DARK, holder.state.value.theme)
        val reopened = PreferencesSettingsStore(preferences()).read()
        assertEquals(AppSettings(ThemeChoice.DARK, TextSizeChoice.LARGEST, notifications = false), reopened)
    }

    @Test
    fun `a stored value this version does not know falls back to the default`() {
        preferences().edit().clear().putString("theme", "SEPIA").commit()

        assertEquals(ThemeChoice.SYSTEM, PreferencesSettingsStore(preferences()).read().theme)
    }

    @Test
    fun `the theme choice decides dark only when it is not the phone's`() {
        assertTrue(ThemeChoice.SYSTEM.isDark(systemDark = true))
        assertFalse(ThemeChoice.LIGHT.isDark(systemDark = true))
        assertTrue(ThemeChoice.DARK.isDark(systemDark = false))
    }
}
