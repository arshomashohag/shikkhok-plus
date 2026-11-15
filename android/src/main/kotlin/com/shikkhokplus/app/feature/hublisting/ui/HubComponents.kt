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

/** The words for a checklist key, or null for a key this client has no words for. */
internal fun checklistLabel(key: String): Int? =
    when (key) {
        "public_name" -> R.string.hub_check_public_name
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
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun AreaDropdown(
    label: String,
    value: String,
    options: List<AreaOption>,
    enabled: Boolean,
    onPick: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val bangla = LocalConfiguration.current.locales[0].language == "bn"
    val name: (AreaOption) -> String = { if (bangla) it.nameBn else it.nameEn }
    val shown = options.firstOrNull { it.code == value }?.let(name).orEmpty()
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
