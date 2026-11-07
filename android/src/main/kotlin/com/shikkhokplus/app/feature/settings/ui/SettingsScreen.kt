package com.shikkhokplus.app.feature.settings.ui

import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.designsystem.MenuIcons
import com.shikkhokplus.app.core.designsystem.MenuRow
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.LocalTouchScale
import com.shikkhokplus.app.core.designsystem.MenuCard
import com.shikkhokplus.app.core.designsystem.MenuDivider
import com.shikkhokplus.app.core.designsystem.MenuSectionHeader
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.settings.AppSettings
import com.shikkhokplus.app.core.settings.LanguageChoice
import com.shikkhokplus.app.core.settings.TextSizeChoice
import com.shikkhokplus.app.core.settings.ThemeChoice

/** The Call for help row. */
const val TAG_SETTINGS_CALL_HELP: String = "settings_call_help"

/** The notifications switch. */
const val TAG_SETTINGS_NOTIFICATIONS: String = "settings_notifications"

/** One theme option, suffixed with the choice's name. */
const val TAG_SETTINGS_THEME: String = "settings_theme_"

/** One text-size option, suffixed with the choice's name. */
const val TAG_SETTINGS_TEXT: String = "settings_text_"

/** One language option, suffixed with the choice's name. */
const val TAG_SETTINGS_LANGUAGE: String = "settings_language_"

/**
 * Settings, reached from More for every role.
 *
 * Four things this phone decides for itself: the language, whether new
 * messages show in the notification tray, light or dark, and how large
 * text is. Each applies the moment it is chosen; a new language redraws
 * the screen in it [C-39].
 *
 * @param settings What is set now
 * @param onChange Called with the settings after a change
 * @param onBack Called to leave
 * @param modifier The layout modifier
 * @param supportPhone The support line, as the release build was given
 *   it, or null to draw no help row
 * @param onCallForHelp Called with the number to dial it
 * @param language The language in effect, or null to draw no language
 *   choice
 * @param onLanguage Called with the language chosen
 */
@Composable
fun SettingsScreen(
    settings: AppSettings,
    onChange: (AppSettings) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    supportPhone: String? = null,
    onCallForHelp: (String) -> Unit = {},
    language: LanguageChoice? = null,
    onLanguage: (LanguageChoice) -> Unit = {},
) {
    ScreenScaffold(title = stringResource(R.string.settings_title), onBack = onBack, modifier = modifier) {
        // First, because someone who cannot read the rest needs it most.
        language?.let { current ->
            Section(stringResource(R.string.settings_section_language)) {
                Choices(
                    options = LanguageChoice.entries,
                    selected = current,
                    label = { stringResource(languageLabel(it)) },
                    tag = { TAG_SETTINGS_LANGUAGE + it.name },
                    onSelect = { if (it != current) onLanguage(it) },
                )
            }
        }
        Section(stringResource(R.string.settings_section_notifications)) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = LocalTouchScale.current.rowSingle)
                    .toggleable(
                        value = settings.notifications,
                        role = Role.Switch,
                        onValueChange = { onChange(settings.copy(notifications = it)) },
                    )
                    .padding(horizontal = 16.dp, vertical = 10.dp)
                    .testTag(TAG_SETTINGS_NOTIFICATIONS),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.settings_notifications), style = MaterialTheme.typography.bodyLarge)
                    Text(
                        stringResource(R.string.settings_notifications_sub),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Switch(checked = settings.notifications, onCheckedChange = null)
            }
        }
        Section(stringResource(R.string.settings_section_theme)) {
            Choices(
                options = ThemeChoice.entries,
                selected = settings.theme,
                label = { stringResource(themeLabel(it)) },
                tag = { TAG_SETTINGS_THEME + it.name },
                onSelect = { onChange(settings.copy(theme = it)) },
            )
        }
        Section(stringResource(R.string.settings_section_text)) {
            Choices(
                options = TextSizeChoice.entries,
                selected = settings.textSize,
                label = { stringResource(textLabel(it)) },
                tag = { TAG_SETTINGS_TEXT + it.name },
                onSelect = { onChange(settings.copy(textSize = it)) },
            )
        }
        // **Call for help** (G4), for every role. Drawn only when the
        // build carries a support number, so no row ever dials nothing.
        supportPhone?.takeIf { it.isNotBlank() }?.let { number ->
            Section(stringResource(R.string.settings_section_help)) {
                MenuRow(
                    title = stringResource(R.string.settings_call_for_help),
                    subtitle = stringResource(R.string.settings_call_for_help_sub, Numerals.phone(number)),
                    icon = MenuIcons.Phone,
                    onClick = { onCallForHelp(number) },
                    modifier = Modifier.testTag(TAG_SETTINGS_CALL_HELP),
                )
            }
        }
    }
}

/**
 * A header over one card.
 *
 * @param header The header
 * @param content The card's rows
 */
@Composable
private fun Section(header: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        MenuSectionHeader(header)
        MenuCard { content() }
    }
}

/**
 * One radio row per option, in a single group.
 *
 * @param options The options, in order
 * @param selected The one chosen
 * @param label Each option's words
 * @param tag Each option's test tag
 * @param onSelect Called with the option tapped
 */
@Composable
private fun <T> Choices(
    options: List<T>,
    selected: T,
    label: @Composable (T) -> String,
    tag: (T) -> String,
    onSelect: (T) -> Unit,
) {
    Column(Modifier.selectableGroup()) {
        options.forEachIndexed { index, option ->
            if (index > 0) MenuDivider()
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = LocalTouchScale.current.rowSingle)
                    .selectable(selected = option == selected, role = Role.RadioButton, onClick = { onSelect(option) })
                    .padding(horizontal = 16.dp)
                    .testTag(tag(option)),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(label(option), style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                RadioButton(selected = option == selected, onClick = null)
            }
        }
    }
}

/**
 * The words for a theme choice.
 *
 * @param choice The choice
 * @return Its string
 */
private fun themeLabel(choice: ThemeChoice): Int =
    when (choice) {
        ThemeChoice.SYSTEM -> R.string.settings_same_as_phone
        ThemeChoice.LIGHT -> R.string.settings_theme_light
        ThemeChoice.DARK -> R.string.settings_theme_dark
    }

/**
 * The words for a language choice.
 *
 * Each language is named in itself, in both bundles, so it can be found
 * by someone who cannot read the language the app is in now.
 *
 * @param choice The choice
 * @return Its string
 */
private fun languageLabel(choice: LanguageChoice): Int =
    when (choice) {
        LanguageChoice.SYSTEM -> R.string.settings_same_as_phone
        LanguageChoice.BANGLA -> R.string.settings_language_bangla
        LanguageChoice.ENGLISH -> R.string.settings_language_english
    }

/**
 * The words for a text-size choice.
 *
 * @param choice The choice
 * @return Its string
 */
private fun textLabel(choice: TextSizeChoice): Int =
    when (choice) {
        TextSizeChoice.SYSTEM -> R.string.settings_same_as_phone
        TextSizeChoice.LARGE -> R.string.settings_text_large
        TextSizeChoice.LARGEST -> R.string.settings_text_largest
    }
