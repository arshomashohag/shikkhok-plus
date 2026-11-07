package com.shikkhokplus.app.feature.settings

import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import com.shikkhokplus.app.feature.settings.ui.TAG_SETTINGS_CALL_HELP
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.settings.AppSettings
import com.shikkhokplus.app.core.settings.InMemorySettingsStore
import com.shikkhokplus.app.core.settings.LanguageChoice
import com.shikkhokplus.app.feature.settings.ui.TAG_SETTINGS_LANGUAGE
import com.shikkhokplus.app.core.settings.SettingsHolder
import com.shikkhokplus.app.core.settings.TextSizeChoice
import com.shikkhokplus.app.core.settings.ThemeChoice
import com.shikkhokplus.app.feature.settings.ui.SettingsScreen
import com.shikkhokplus.app.feature.settings.ui.TAG_SETTINGS_NOTIFICATIONS
import com.shikkhokplus.app.feature.settings.ui.TAG_SETTINGS_TEXT
import com.shikkhokplus.app.feature.settings.ui.TAG_SETTINGS_THEME
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/** Settings, rendered: each choice shows what is set and changes it. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class SettingsScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun render(holder: SettingsHolder) {
        compose.setContent {
            val settings by holder.state.collectAsState()
            ShikkhokTheme {
                SettingsScreen(settings = settings, onChange = { next -> holder.update { next } }, onBack = {})
            }
        }
    }

    @Test
    fun `it shows what is set now`() {
        render(SettingsHolder(InMemorySettingsStore(AppSettings(theme = ThemeChoice.DARK))))

        compose.onNodeWithText("Settings").assertExists()
        compose.onNodeWithTag(TAG_SETTINGS_NOTIFICATIONS).assertIsOn()
        compose.onNodeWithTag(TAG_SETTINGS_THEME + "DARK").assertIsSelected()
        compose.onNodeWithTag(TAG_SETTINGS_TEXT + "SYSTEM").performScrollTo().assertIsSelected()
    }

    @Test
    fun `turning notifications off, and picking a theme and a size, changes the settings`() {
        val holder = SettingsHolder(InMemorySettingsStore())
        render(holder)

        compose.onNodeWithTag(TAG_SETTINGS_NOTIFICATIONS).performClick()
        compose.onNodeWithTag(TAG_SETTINGS_THEME + "LIGHT").performClick()
        compose.onNodeWithTag(TAG_SETTINGS_TEXT + "LARGE").performScrollTo().performClick()

        compose.onNodeWithTag(TAG_SETTINGS_NOTIFICATIONS).assertIsOff()
        assertEquals(AppSettings(ThemeChoice.LIGHT, TextSizeChoice.LARGE, notifications = false), holder.state.value)
    }

    @Test
    fun `call for help dials the build's support number, and is absent without one`() {
        // Every role reaches Settings, so every role gets the row; a
        // build with no number draws none rather than a row dialling nothing.
        val dialled = mutableListOf<String>()
        var number by mutableStateOf<String?>(null)
        compose.setContent {
            ShikkhokTheme {
                SettingsScreen(
                    settings = AppSettings(),
                    onChange = {},
                    onBack = {},
                    supportPhone = number,
                    onCallForHelp = { dialled += it },
                )
            }
        }
        compose.onNodeWithTag(TAG_SETTINGS_CALL_HELP).assertDoesNotExist()

        number = "+8801711234567"
        compose.waitForIdle()
        compose.onNodeWithTag(TAG_SETTINGS_CALL_HELP).performScrollTo().performClick()

        assertEquals(listOf("+8801711234567"), dialled)
    }

    @Test
    fun `the language choice shows what is in effect and asks for a new one`() {
        // C-39: an English-system phone must be able to reach Bangla from
        // inside the app, and each language is named in itself.
        val chosen = mutableListOf<LanguageChoice>()
        compose.setContent {
            ShikkhokTheme {
                SettingsScreen(
                    settings = AppSettings(),
                    onChange = {},
                    onBack = {},
                    language = LanguageChoice.ENGLISH,
                    onLanguage = { chosen += it },
                )
            }
        }

        compose.onNodeWithTag(TAG_SETTINGS_LANGUAGE + "ENGLISH").assertIsSelected()
        compose.onNodeWithText("বাংলা").assertExists()

        compose.onNodeWithTag(TAG_SETTINGS_LANGUAGE + "ENGLISH").performClick()
        compose.onNodeWithTag(TAG_SETTINGS_LANGUAGE + "BANGLA").performClick()

        assertEquals(listOf(LanguageChoice.BANGLA), chosen, "choosing the language in effect asks for nothing")
    }

    @Test
    fun `no language choice is drawn when none is supplied`() {
        render(SettingsHolder(InMemorySettingsStore()))

        compose.onNodeWithTag(TAG_SETTINGS_LANGUAGE + "BANGLA").assertDoesNotExist()
    }
}
