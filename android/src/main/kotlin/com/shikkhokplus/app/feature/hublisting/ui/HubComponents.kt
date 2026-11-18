package com.shikkhokplus.app.feature.hublisting.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.feature.hublisting.AreaOption
import com.shikkhokplus.app.feature.hublisting.ClassLevel
import com.shikkhokplus.app.feature.hublisting.Curriculum
import com.shikkhokplus.app.feature.hublisting.ListingStatus

/** What a status chip is called, by its status. */
internal fun statusLabel(status: ListingStatus): Int =
    when (status) {
        ListingStatus.DRAFT -> R.string.hub_status_draft
        ListingStatus.PUBLISHED -> R.string.hub_status_published
        ListingStatus.HIDDEN -> R.string.hub_status_hidden
        ListingStatus.SUSPENDED -> R.string.hub_status_suspended
        ListingStatus.UNKNOWN -> R.string.error_unexpected
    }

/** What a teaching mode or batch mode is called, by its wire value. */
internal fun modeLabel(wire: String): Int =
    when (wire) {
        "home_visit" -> R.string.hub_mode_home_visit
        "online" -> R.string.hub_mode_online
        else -> R.string.hub_mode_in_person
    }

/** What an admissions state is called, by its wire value. */
internal fun admissionsLabel(wire: String): Int =
    when (wire) {
        "waitlist" -> R.string.hub_batch_admissions_waitlist
        "closed" -> R.string.hub_batch_admissions_closed
        else -> R.string.hub_batch_admissions_open
    }

/** Each class level's words; every [ClassLevel] has an entry, which a test asserts. */
private val LEVEL_LABELS: Map<ClassLevel, Int> =
    mapOf(
        ClassLevel.CLASS_1 to R.string.hub_level_class_1,
        ClassLevel.CLASS_2 to R.string.hub_level_class_2,
        ClassLevel.CLASS_3 to R.string.hub_level_class_3,
        ClassLevel.CLASS_4 to R.string.hub_level_class_4,
        ClassLevel.CLASS_5 to R.string.hub_level_class_5,
        ClassLevel.CLASS_6 to R.string.hub_level_class_6,
        ClassLevel.CLASS_7 to R.string.hub_level_class_7,
        ClassLevel.CLASS_8 to R.string.hub_level_class_8,
        ClassLevel.CLASS_9 to R.string.hub_level_class_9,
        ClassLevel.CLASS_10 to R.string.hub_level_class_10,
        ClassLevel.CLASS_11 to R.string.hub_level_class_11,
        ClassLevel.CLASS_12 to R.string.hub_level_class_12,
        ClassLevel.SSC to R.string.hub_level_ssc,
        ClassLevel.HSC to R.string.hub_level_hsc,
        ClassLevel.ADMISSION to R.string.hub_level_admission,
        ClassLevel.O_LEVEL to R.string.hub_level_o_level,
        ClassLevel.A_LEVEL to R.string.hub_level_a_level,
        ClassLevel.OTHER to R.string.hub_level_other,
    )

/** What a class level is called, by its vocabulary entry. */
internal fun levelLabel(level: ClassLevel): Int = LEVEL_LABELS.getValue(level)

/** What a curriculum is called, by its vocabulary entry. */
internal fun curriculumLabel(curriculum: Curriculum): Int =
    when (curriculum) {
        Curriculum.NATIONAL_BANGLA -> R.string.hub_curriculum_national_bangla
        Curriculum.NATIONAL_ENGLISH -> R.string.hub_curriculum_national_english
        Curriculum.ENGLISH_MEDIUM -> R.string.hub_curriculum_english_medium
        Curriculum.MADRASAH -> R.string.hub_curriculum_madrasah
        Curriculum.OTHER -> R.string.hub_curriculum_other
    }

/**
 * A batch's saved class levels and curriculum in the reader's words, never
 * the raw values. A value this version does not know is left out.
 *
 * @param levels The server's `class_levels`
 * @param curriculum The server's `curriculum`
 * @return "Class 9, HSC · Madrasah", or an empty string for neither
 */
@Composable
internal fun levelsLine(levels: List<String>, curriculum: String?): String {
    val names =
        levels.mapNotNull { wire -> ClassLevel.entries.firstOrNull { it.wire == wire } }
            .map { stringResource(levelLabel(it)) }
            .joinToString(", ")
    val course =
        Curriculum.entries.firstOrNull { it.wire == curriculum }?.let { stringResource(curriculumLabel(it)) }.orEmpty()
    return listOf(names, course).filter { it.isNotEmpty() }.joinToString(" · ")
}

/** The words for a checklist key, or null for a key this client has no words for. */
internal fun checklistLabel(key: String): Int? =
    when (key) {
        "public_name" -> R.string.hub_check_public_name
        "public_title" -> R.string.hub_check_public_title
        "slug" -> R.string.hub_check_slug
        "area" -> R.string.hub_check_area
        "headline" -> R.string.hub_check_headline
        "bio" -> R.string.hub_check_bio
        "contact_or_none" -> R.string.hub_check_contact_or_none
        "description" -> R.string.hub_check_description
        "class_levels" -> R.string.hub_check_class_levels
        "subjects" -> R.string.hub_check_subjects
        "mode" -> R.string.hub_check_mode
        else -> null
    }

/**
 * A status chip and, when the server says the owner earned it, the Runs
 * classes badge. Both are the server's words, not computed here.
 *
 * @param status The listing's status
 * @param runsClasses Whether the server says the badge is earned
 */
@Composable
internal fun StatusRow(status: ListingStatus, runsClasses: Boolean) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
        Pill(stringResource(statusLabel(status)))
        if (runsClasses) Pill(stringResource(R.string.hub_badge_runs_classes), Modifier.testTag(TAG_HUB_BADGE))
    }
}

/** A small rounded label. */
@Composable
internal fun Pill(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.onSecondaryContainer,
        modifier =
            modifier
                .background(MaterialTheme.colorScheme.secondaryContainer, MaterialTheme.shapes.small)
                .padding(horizontal = 10.dp, vertical = 4.dp),
    )
}

/**
 * A pick-one list of areas, drawn in the reader's language. The list is
 * the server's; the box shows the chosen area's name, or nothing.
 *
 * @param label The label
 * @param value The chosen area's code, or empty
 * @param options The server's areas
 * @param enabled Whether it can be changed
 * @param onPick Called with the chosen code
 * @param none When given, an empty choice with this text, picked as an empty code
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun AreaDropdown(
    label: String,
    value: String,
    options: List<AreaOption>,
    enabled: Boolean,
    onPick: (String) -> Unit,
    none: String? = null,
) {
    var expanded by remember { mutableStateOf(false) }
    val bangla = LocalConfiguration.current.locales[0].language == "bn"
    val name: (AreaOption) -> String = { if (bangla) it.nameBn else it.nameEn }
    val shown = options.firstOrNull { it.code == value }?.let(name) ?: none.takeIf { value.isEmpty() }.orEmpty()
    ExposedDropdownMenuBox(expanded = expanded && enabled, onExpandedChange = { expanded = it && enabled }) {
        OutlinedTextField(
            value = shown,
            onValueChange = {},
            readOnly = true,
            enabled = enabled,
            label = { Text(label) },
            placeholder = { Text(stringResource(R.string.hub_area_choose)) },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable).testTag("hub_area_$label"),
        )
        ExposedDropdownMenu(expanded = expanded && enabled, onDismissRequest = { expanded = false }) {
            if (none != null) {
                DropdownMenuItem(
                    text = { Text(none, color = MaterialTheme.colorScheme.onSurface) },
                    onClick = {
                        onPick("")
                        expanded = false
                    },
                )
            }
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(name(option), color = MaterialTheme.colorScheme.onSurface) },
                    onClick = {
                        onPick(option.code)
                        expanded = false
                    },
                )
            }
        }
    }
}
