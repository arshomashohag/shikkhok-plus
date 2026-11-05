package com.shikkhokplus.app.core.settings

import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Light or dark, or whatever the phone is set to. */
enum class ThemeChoice {
    /** Follow the phone. */
    SYSTEM,

    /** Always light. */
    LIGHT,

    /** Always dark. */
    DARK,
    ;

    /**
     * Whether to draw dark.
     *
     * @param systemDark Whether the phone is in dark mode
     * @return True for the dark scheme
     */
    fun isDark(systemDark: Boolean): Boolean =
        when (this) {
            SYSTEM -> systemDark
            LIGHT -> false
            DARK -> true
        }
}

/**
 * How large the app's text is, on top of the phone's own setting.
 *
 * @property scale The factor applied to the phone's font scale
 */
enum class TextSizeChoice(val scale: Float) {
    /** The phone's own size. */
    SYSTEM(1.0f),

    /** A step larger. */
    LARGE(1.15f),

    /** Two steps larger. */
    LARGEST(1.3f),
}

/**
 * The person's own preferences for this phone.
 *
 * **Presentation only.** Nothing here is a business rule or reaches
 * the server; they are how this phone draws the app and whether it
 * shows notifications in the tray [TC-9].
 *
 * @property theme Light, dark or the phone's choice
 * @property textSize How large text is drawn
 * @property notifications Whether new inbox messages appear in the
 *   phone's notification tray
 */
data class AppSettings(
    val theme: ThemeChoice = ThemeChoice.SYSTEM,
    val textSize: TextSizeChoice = TextSizeChoice.SYSTEM,
    val notifications: Boolean = true,
)

/** Where [AppSettings] are kept between launches. */
interface SettingsStore {
    /**
     * The stored settings, or the defaults when none are stored.
     *
     * @return The settings
     */
    fun read(): AppSettings

    /**
     * Keep these settings.
     *
     * @param settings What to keep
     */
    fun write(settings: AppSettings)
}

/** Settings held in memory only, for tests and previews. */
class InMemorySettingsStore(private var settings: AppSettings = AppSettings()) : SettingsStore {
    override fun read(): AppSettings = settings

    override fun write(settings: AppSettings) {
        this.settings = settings
    }
}

/**
 * Settings in the app's own preferences file.
 *
 * **Plain, not encrypted**: a theme and a text size identify nobody and
 * hold no child's data, unlike the token store. An unknown stored value
 * (a later version's choice, say) falls back to the default rather than
 * failing.
 *
 * @param preferences The preferences file
 */
class PreferencesSettingsStore(private val preferences: SharedPreferences) : SettingsStore {
    override fun read(): AppSettings =
        AppSettings(
            theme = enumOr(preferences.getString(KEY_THEME, null), ThemeChoice.SYSTEM),
            textSize = enumOr(preferences.getString(KEY_TEXT_SIZE, null), TextSizeChoice.SYSTEM),
            notifications = preferences.getBoolean(KEY_NOTIFICATIONS, true),
        )

    override fun write(settings: AppSettings) {
        preferences
            .edit()
            .putString(KEY_THEME, settings.theme.name)
            .putString(KEY_TEXT_SIZE, settings.textSize.name)
            .putBoolean(KEY_NOTIFICATIONS, settings.notifications)
            .apply()
    }

    private companion object {
        const val KEY_THEME = "theme"
        const val KEY_TEXT_SIZE = "text_size"
        const val KEY_NOTIFICATIONS = "notifications"

        inline fun <reified E : Enum<E>> enumOr(stored: String?, fallback: E): E =
            enumValues<E>().firstOrNull { it.name == stored } ?: fallback
    }
}

/**
 * The live settings, shared by the theme and the Settings screen.
 *
 * @param store Where they are kept
 */
class SettingsHolder(private val store: SettingsStore) {
    private val current = MutableStateFlow(store.read())

    /** The settings now. */
    val state: StateFlow<AppSettings> = current.asStateFlow()

    /**
     * Change the settings and keep the change.
     *
     * @param change What to change
     */
    fun update(change: (AppSettings) -> AppSettings) {
        val next = change(current.value)
        store.write(next)
        current.value = next
    }
}
