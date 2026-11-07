package com.shikkhokplus.app.core.settings

import android.app.Activity
import android.app.LocaleManager
import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.os.Build
import android.os.LocaleList
import java.util.Locale

/**
 * Which language the app is drawn in.
 *
 * @property tag The BCP 47 language tag, or null to follow the phone
 */
enum class LanguageChoice(val tag: String?) {
    /** Whatever the phone is set to. */
    SYSTEM(null),

    /** Bangla, the product's first language [TC-15, D-43]. */
    BANGLA("bn"),

    /** English. */
    ENGLISH("en"),
    ;

    companion object {
        /**
         * The choice a set of app locales stands for.
         *
         * @param language The first app locale's language, or null when
         *   the app follows the phone
         * @return The matching choice; a language the app does not ship
         *   reads as following the phone
         */
        fun ofLanguage(language: String?): LanguageChoice =
            entries.firstOrNull { it.tag != null && it.tag == language } ?: SYSTEM

        /**
         * What a phone with no choice recorded starts in.
         *
         * **Bangla on a fresh install, the phone's language on an
         * update** [C-39]. English-system phones are common in
         * Bangladesh, and a Bangla-first product that opens in English
         * on them is not Bangla-first; the web client already defaults
         * to Bangla. Someone who already uses the app is not switched
         * under their feet by an update, and either can change it in
         * Settings.
         *
         * @param freshInstall Whether this build is the first one
         *   installed on the phone
         * @return The starting choice
         */
        fun firstLaunchDefault(freshInstall: Boolean): LanguageChoice = if (freshInstall) BANGLA else SYSTEM
    }
}

/**
 * Applies the app's own language choice, on every supported Android.
 *
 * **Android 13 and later: the platform's per-app language**, through
 * `LocaleManager`. The platform keeps the choice, recreates the screen,
 * and offers the same choice in the phone's own Settings, which is what
 * `res/xml/locales_config.xml` lists the languages for. The platform is
 * the source of truth there, so a change made in the phone's Settings
 * shows here too.
 *
 * **Android 12 and earlier: a configuration context**, since those
 * releases have no per-app language. The choice is kept in this app's
 * preferences and applied in `MainActivity.attachBaseContext`, which is
 * the documented way to give an Activity resources in another locale.
 * What is drawn outside the Activity -- the tray notification, built
 * from the application context -- follows the phone on those releases.
 *
 * Taken without AppCompat on purpose: `AppCompatDelegate` would add a
 * dependency and require an `AppCompatActivity` and an AppCompat theme
 * for the same two code paths written out here.
 */
object AppLanguage {
    private const val FILE = "language"
    private const val KEY_CHOICE = "choice"

    /**
     * The choice in effect now, for the Settings screen.
     *
     * @param context Any context
     * @return The current choice
     */
    fun current(context: Context): LanguageChoice =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val locales = context.getSystemService(LocaleManager::class.java)?.applicationLocales
            LanguageChoice.ofLanguage(locales?.takeUnless { it.isEmpty }?.get(0)?.language)
        } else {
            stored(context)
        }

    /**
     * Change the language and redraw the screen in it.
     *
     * @param context A context inside the Activity
     * @param choice The new choice
     */
    fun choose(context: Context, choice: LanguageChoice) {
        prefs(context).edit().putString(KEY_CHOICE, choice.name).apply()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            // The platform recreates the Activity itself.
            context.getSystemService(LocaleManager::class.java)?.applicationLocales = localesOf(choice)
        } else {
            context.findActivity()?.recreate()
        }
    }

    /**
     * Wrap an Activity's base context in the chosen language, before
     * Android 13. A no-op from 13 on, where the platform does it.
     *
     * @param base The context the Activity was given
     * @return The context to attach
     */
    fun wrap(base: Context): Context {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) return base
        val tag = stored(base).tag ?: return base
        val configuration = Configuration(base.resources.configuration)
        configuration.setLocales(LocaleList(Locale.forLanguageTag(tag)))
        return base.createConfigurationContext(configuration)
    }

    /**
     * Apply the first-launch default on Android 13 and later, once.
     *
     * Before 13 the default is applied by [wrap], which runs first. From
     * 13 on, the platform holds the choice, so a fresh install that
     * should open in Bangla asks for it here; the platform then recreates
     * the Activity in Bangla. Never repeated, so a later "same as phone"
     * -- here or in the phone's Settings -- is respected.
     *
     * @param context The Activity
     */
    fun applyFirstLaunchDefault(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        if (prefs(context).contains(KEY_CHOICE)) return
        val choice = stored(context)
        val manager = context.getSystemService(LocaleManager::class.java) ?: return
        if (choice != LanguageChoice.SYSTEM && manager.applicationLocales.isEmpty) {
            manager.applicationLocales = localesOf(choice)
        }
    }

    /**
     * The stored choice, recording the first-launch default when none is.
     *
     * @param context Any context
     * @return The choice
     */
    private fun stored(context: Context): LanguageChoice {
        val preferences = prefs(context)
        val name = preferences.getString(KEY_CHOICE, null)
        LanguageChoice.entries.firstOrNull { it.name == name }?.let { return it }
        val initial = LanguageChoice.firstLaunchDefault(isFreshInstall(context))
        preferences.edit().putString(KEY_CHOICE, initial.name).apply()
        return initial
    }

    private fun prefs(context: Context): SharedPreferences = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    private fun localesOf(choice: LanguageChoice): LocaleList =
        choice.tag?.let { LocaleList.forLanguageTags(it) } ?: LocaleList.getEmptyLocaleList()

    /**
     * Whether this is the first build installed, rather than an update.
     *
     * @param context Any context
     * @return True when the install and last-update times are equal
     */
    private fun isFreshInstall(context: Context): Boolean =
        try {
            val info =
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    context.packageManager.getPackageInfo(context.packageName, PackageManager.PackageInfoFlags.of(0))
                } else {
                    @Suppress("DEPRECATION")
                    context.packageManager.getPackageInfo(context.packageName, 0)
                }
            info.firstInstallTime == info.lastUpdateTime
        } catch (_: PackageManager.NameNotFoundException) {
            // Cannot tell: leave the phone's language alone.
            false
        }

    private tailrec fun Context.findActivity(): Activity? =
        when (this) {
            is Activity -> this
            is ContextWrapper -> baseContext.findActivity()
            else -> null
        }
}
