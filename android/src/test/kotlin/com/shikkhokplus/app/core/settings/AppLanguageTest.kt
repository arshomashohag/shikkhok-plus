package com.shikkhokplus.app.core.settings

import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The app can be drawn in Bangla whatever the phone's language [C-39].
 *
 * The platform halves -- `LocaleManager` and the configuration context
 * -- are Android's own and are not re-tested here; what is asserted is
 * this app's part: which choices exist, what a fresh install starts in,
 * and that every language offered has a bundle to be drawn from.
 */
class AppLanguageTest {

    private val main = File("src/main")

    @Test
    fun `a fresh install starts in Bangla and an update keeps the phone's language`() {
        assertEquals(LanguageChoice.BANGLA, LanguageChoice.firstLaunchDefault(freshInstall = true))
        assertEquals(LanguageChoice.SYSTEM, LanguageChoice.firstLaunchDefault(freshInstall = false))
    }

    @Test
    fun `app locales map to the choice they stand for`() {
        assertEquals(LanguageChoice.BANGLA, LanguageChoice.ofLanguage("bn"))
        assertEquals(LanguageChoice.ENGLISH, LanguageChoice.ofLanguage("en"))
        assertEquals(LanguageChoice.SYSTEM, LanguageChoice.ofLanguage(null))
        // A language the app does not ship is not a choice it can show
        // as selected; the screen then reads as following the phone.
        assertEquals(LanguageChoice.SYSTEM, LanguageChoice.ofLanguage("hi"))
    }

    @Test
    fun `every language offered to the phone has a bundle, and every bundle is offered`() {
        val config = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
            .newDocumentBuilder().parse(File(main, "res/xml/locales_config.xml")).documentElement
        val nodes = config.getElementsByTagName("locale")
        val offered =
            (0 until nodes.length).map {
                (nodes.item(it) as Element).getAttributeNS(ANDROID_NS, "name")
            }

        assertEquals(listOf("bn", "en"), offered, "Bangla first")
        assertTrue(File(main, "res/values-bn/strings.xml").exists())
        assertEquals(
            LanguageChoice.entries.mapNotNull { it.tag }.toSet(),
            offered.toSet(),
            "the in-app choice and the phone's per-app choice offer the same languages",
        )
    }

    @Test
    fun `the manifest declares the locale config`() {
        val manifest = File(main, "AndroidManifest.xml").readText()
        assertTrue(manifest.contains("""android:localeConfig="@xml/locales_config""""))
    }

    private companion object {
        const val ANDROID_NS = "http://schemas.android.com/apk/res/android"
    }
}
