package com.shikkhokplus.app.core.session.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ListScreenScaffold
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.core.session.LensOption

/** The picker's list. */
const val TAG_LENS_PICKER: String = "lens_picker"

/** One offered lens. */
const val TAG_LENS_OPTION: String = "lens_option"

/**
 * Which role to continue as, when a person holds more than one.
 *
 * **Shown only for two or more.** The server sends no default lens
 * [TC-11, D-2] and documents a single-entry list as the cue to skip
 * this screen, so a person with one lens never sees it — asking
 * someone to choose between one thing is a tap that teaches them
 * nothing.
 *
 * **The counts are the server's and are what distinguish the rows.**
 * "Teacher" and "Guardian" name roles; "3 classes" and "1 child" are
 * what let a parent-teacher tell at a glance which is which.
 *
 * @param options Every lens, in the server's fixed order
 * @param onChoose Called with the lens the person picked
 * @param modifier The layout modifier
 */
@Composable
fun LensPickerScreen(
    options: List<LensOption>,
    onChoose: (Lens) -> Unit,
    modifier: Modifier = Modifier,
) {
    ListScreenScaffold(
        title = stringResource(R.string.lens_picker_title),
        subtitle = stringResource(R.string.lens_picker_subtitle),
        modifier = modifier,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().testTag(TAG_LENS_PICKER),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // Rendered in the order given. Sorting here would reshuffle
            // the picker between sign-ins as counts change, which the
            // server's fixed order exists to prevent.
            options.forEach { option ->
                LensRow(option, onChoose)
            }
        }
    }
}

/**
 * One choosable lens.
 *
 * @param option The lens and its count
 * @param onChoose Called when this row is tapped
 */
@Composable
private fun LensRow(
    option: LensOption,
    onChoose: (Lens) -> Unit,
) {
    Card(
        modifier =
            Modifier
                .fillMaxWidth()
                .testTag(TAG_LENS_OPTION)
                // A card that acts as a button says so, or a screen
                // reader announces it as inert text.
                .semantics { role = Role.Button }
                .clickable { onChoose(option.lens) },
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = stringResource(labelOf(option.lens)),
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text =
                    stringResource(
                        countLabelOf(option.lens),
                        Numerals.count(option.count),
                    ),
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

/**
 * Name one lens.
 *
 * An exhaustive `when` rather than a map, so a fourth lens fails to
 * compile instead of rendering as whichever branch was the fallback.
 *
 * @param lens The lens to name
 * @return Its string resource
 */
private fun labelOf(lens: Lens): Int =
    when (lens) {
        Lens.TEACHER -> R.string.lens_teacher
        Lens.STUDENT -> R.string.lens_student
        Lens.GUARDIAN -> R.string.lens_guardian
    }

/**
 * Name what sits behind one lens.
 *
 * Each lens counts a different thing — classes, enrolments, children
 * — so one shared "%1$s items" would be wrong for all three.
 *
 * @param lens The lens to describe
 * @return Its count string resource
 */
private fun countLabelOf(lens: Lens): Int =
    when (lens) {
        Lens.TEACHER -> R.string.lens_teacher_count
        Lens.STUDENT -> R.string.lens_student_count
        Lens.GUARDIAN -> R.string.lens_guardian_count
    }
