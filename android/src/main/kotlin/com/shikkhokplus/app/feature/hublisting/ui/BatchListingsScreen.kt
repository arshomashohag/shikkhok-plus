package com.shikkhokplus.app.feature.hublisting.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.EmptyState
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.Reach
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hublisting.Admissions
import com.shikkhokplus.app.feature.hublisting.BatchDraft
import com.shikkhokplus.app.feature.hublisting.BatchEditorState
import com.shikkhokplus.app.feature.hublisting.BatchListingResponse
import com.shikkhokplus.app.feature.hublisting.BatchListingsBody
import com.shikkhokplus.app.feature.hublisting.BatchListingsState
import com.shikkhokplus.app.feature.hublisting.ClassLevel
import com.shikkhokplus.app.feature.hublisting.Curriculum
import com.shikkhokplus.app.feature.hublisting.HubLimits
import com.shikkhokplus.app.feature.hublisting.ListingStatus
import com.shikkhokplus.app.feature.hublisting.TeachingMode
import com.shikkhokplus.app.feature.hublisting.teacherLine

/** The batch editor's Save button. */
const val TAG_BATCH_SAVE: String = "batch_listing_save"

/** The batch editor's Publish button. */
const val TAG_BATCH_PUBLISH: String = "batch_listing_publish"

/** The batch editor's Unpublish button. */
const val TAG_BATCH_UNPUBLISH: String = "batch_listing_unpublish"

/** The batch editor's "Photos": opens that batch's photo gallery. */
const val TAG_BATCH_PHOTOS: String = "batch_listing_photos"

/**
 * Tag for one batch's edit row.
 *
 * @param batchId The batch
 * @return The tag
 */
fun batchListingRowTag(batchId: String): String = "batch_listing_$batchId"

/**
 * What the batch listings screen's controls call.
 *
 * @property onEdit Opens one batch's editor
 * @property onClose Closes the editor
 * @property onChange Changes what is typed
 * @property onSave Sends the form
 * @property onPublish Publishes the batch
 * @property onUnpublish Takes it down
 * @property onPhotos Opens a batch's photos: the batch, and true when its
 *   listing is suspended, so the gallery opens read-only
 * @property onRetry Repeats what last failed
 * @property onBack Leaves the screen
 */
data class BatchListingsActions(
    val onEdit: (String) -> Unit = {},
    val onClose: () -> Unit = {},
    val onChange: ((BatchDraft) -> BatchDraft) -> Unit = {},
    val onSave: () -> Unit = {},
    val onPublish: () -> Unit = {},
    val onUnpublish: () -> Unit = {},
    val onPhotos: (String, Boolean) -> Unit = { _, _ -> },
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The batches on the owner's public page: each batch's listing state and
 * an editor sheet.
 *
 * The fee is the server's money string, shown as it arrived and present
 * only while the owner chose to show it. Teacher names are the server's,
 * with its "Centre faculty" fallback shown in the reader's language.
 * Long Bangla batch names wrap; nothing here is truncated.
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun BatchListingsScreen(
    state: BatchListingsState,
    actions: BatchListingsActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.hub_batches_title), modifier = modifier, onBack = actions.onBack) {
        when (val body = state.body) {
            BatchListingsBody.Loading -> SkeletonList(rows = 3)
            is BatchListingsBody.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = null,
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) actions.onRetry else null,
                )
            is BatchListingsBody.Loaded -> {
                Text(
                    stringResource(R.string.hub_batches_owner_first),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (body.batches.isEmpty()) {
                    EmptyState(
                        title = stringResource(R.string.hub_batches_title),
                        body = stringResource(R.string.hub_batches_empty),
                    )
                }
                body.batches.forEach { BatchRow(it) { actions.onEdit(it.batchId) } }
            }
        }
    }
    state.editor?.let { BatchEditorSheet(it, actions) }
}

@Composable
private fun BatchRow(batch: BatchListingResponse, onEdit: () -> Unit) {
    ShikkhokCard(onClick = onEdit, modifier = Modifier.testTag(batchListingRowTag(batch.batchId))) {
        Text(batch.batchName, style = MaterialTheme.typography.titleMedium)
        Text(
            batch.subjects.joinToString(", "),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        val levels = levelsLine(batch.classLevels, batch.curriculum)
        if (levels.isNotEmpty()) {
            Text(
                levels,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(
            batch.fee?.let { stringResource(R.string.hub_batch_fee, it.toString()) }
                ?: stringResource(R.string.hub_batch_fee_hidden),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (batch.teacherNames.isNotEmpty()) {
            Text(
                stringResource(
                    R.string.hub_batch_teachers,
                    teacherLine(batch.teacherNames, stringResource(R.string.hub_centre_faculty)),
                ),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Row(
            horizontalArrangement = Arrangement.spacedBy(Spacing.tight),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Pill(stringResource(statusLabel(ListingStatus.fromWire(batch.status))))
            Text(
                stringResource(R.string.hub_batch_edit),
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.heightIn(min = Reach.touch).padding(Spacing.tight),
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BatchEditorSheet(editor: BatchEditorState, actions: BatchListingsActions) {
    ModalBottomSheet(
        onDismissRequest = actions.onClose,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = MaterialTheme.colorScheme.surface,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(start = Spacing.screen, end = Spacing.screen, bottom = Spacing.section),
            verticalArrangement = Arrangement.spacedBy(Spacing.listItem),
        ) {
            Text(editor.batch.batchName, style = MaterialTheme.typography.titleLarge, modifier = Modifier.asHeading())
            Text(
                stringResource(R.string.hub_batch_edit_title),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            StatusRow(ListingStatus.fromWire(editor.batch.status), runsClasses = false)
            if (editor.readOnly) {
                Banner(
                    title = stringResource(R.string.hub_suspended_title),
                    body = stringResource(R.string.hub_suspended_body),
                    tone = BannerTone.ERROR,
                )
            }
            ChecklistCard(editor.batch.checklist)
            BatchFields(editor, actions)
            TextAction(
                stringResource(R.string.hub_photos_title),
                { actions.onPhotos(editor.batch.batchId, editor.readOnly) },
                Modifier.fillMaxWidth().testTag(TAG_BATCH_PHOTOS),
            )
            editor.failure?.let { FailureBanner(it, actions.onRetry) }
            BatchButtons(editor, actions)
            SecondaryButton(
                text = stringResource(R.string.action_cancel),
                onClick = actions.onClose,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BatchFields(editor: BatchEditorState, actions: BatchListingsActions) {
    val d = editor.draft
    val on = !editor.readOnly
    ShikkhokTextField(
        d.publicTitle,
        { v -> actions.onChange { it.copy(publicTitle = v.take(HubLimits.PUBLIC_TITLE)) } },
        stringResource(R.string.hub_batch_field_public_title),
        help = stringResource(R.string.hub_batch_public_title_help),
        enabled = on,
    )
    ShikkhokTextField(
        d.slug,
        { v -> actions.onChange { it.copy(slug = v.take(HubLimits.SLUG)) } },
        stringResource(R.string.hub_field_slug),
        help = stringResource(R.string.hub_slug_help),
        enabled = on,
    )
    LongField(d.descriptionEn, R.string.hub_batch_field_description_en, on) { v ->
        actions.onChange { it.copy(descriptionEn = v.take(HubLimits.DESCRIPTION)) }
    }
    LongField(d.descriptionBn, R.string.hub_batch_field_description_bn, on) { v ->
        actions.onChange { it.copy(descriptionBn = v.take(HubLimits.DESCRIPTION)) }
    }
    LongField(d.syllabusEn, R.string.hub_batch_field_syllabus_en, on) { v ->
        actions.onChange { it.copy(syllabusEn = v.take(HubLimits.SYLLABUS)) }
    }
    LongField(d.syllabusBn, R.string.hub_batch_field_syllabus_bn, on) { v ->
        actions.onChange { it.copy(syllabusBn = v.take(HubLimits.SYLLABUS)) }
    }
    // The closed vocabularies as chips: nothing typed, nothing the server refuses.
    Text(stringResource(R.string.hub_batch_field_levels), style = MaterialTheme.typography.labelLarge)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
        ClassLevel.entries.forEach { level ->
            val picked = level.wire in d.levels
            FilterChip(
                selected = picked,
                onClick = {
                    actions.onChange { d ->
                        d.copy(levels = if (picked) d.levels - level.wire else d.levels + level.wire)
                    }
                },
                enabled = on,
                label = { Text(stringResource(levelLabel(level))) },
            )
        }
    }
    Text(stringResource(R.string.hub_batch_field_curriculum), style = MaterialTheme.typography.labelLarge)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
        FilterChip(
            selected = d.curriculum.isEmpty(),
            onClick = { actions.onChange { it.copy(curriculum = "") } },
            enabled = on,
            label = { Text(stringResource(R.string.hub_batch_curriculum_none)) },
        )
        Curriculum.entries.forEach { course ->
            FilterChip(
                selected = d.curriculum == course.wire,
                onClick = { actions.onChange { it.copy(curriculum = course.wire) } },
                enabled = on,
                label = { Text(stringResource(curriculumLabel(course))) },
            )
        }
    }
    ShikkhokTextField(
        d.tags,
        { v -> actions.onChange { it.copy(tags = v) } },
        stringResource(R.string.hub_batch_field_tags),
        help = stringResource(R.string.hub_batch_tags_help),
        enabled = on,
    )
    Text(stringResource(R.string.hub_batch_field_mode), style = MaterialTheme.typography.labelLarge)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
        FilterChip(
            selected = d.mode.isEmpty(),
            onClick = { actions.onChange { it.copy(mode = "") } },
            enabled = on,
            label = { Text(stringResource(R.string.hub_batch_mode_none)) },
        )
        TeachingMode.entries.forEach { mode ->
            FilterChip(
                selected = d.mode == mode.wire,
                onClick = { actions.onChange { it.copy(mode = mode.wire) } },
                enabled = on,
                label = { Text(stringResource(modeLabel(mode.wire))) },
            )
        }
    }
    Text(stringResource(R.string.hub_batch_field_admissions), style = MaterialTheme.typography.labelLarge)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
        Admissions.entries.forEach { a ->
            FilterChip(
                selected = d.admissions == a.wire,
                onClick = { actions.onChange { it.copy(admissions = a.wire) } },
                enabled = on,
                label = { Text(stringResource(admissionsLabel(a.wire))) },
            )
        }
    }
    CheckRow(d.showFee, R.string.hub_batch_show_fee, on) { v -> actions.onChange { it.copy(showFee = v) } }
    CheckRow(d.showSchedule, R.string.hub_batch_show_schedule, on) { v ->
        actions.onChange { it.copy(showSchedule = v) }
    }
    if (editor.batch.showFee == null) {
        Text(
            stringResource(R.string.hub_batch_flags_help),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun LongField(value: String, label: Int, enabled: Boolean, onChange: (String) -> Unit) {
    ShikkhokTextField(
        value = value,
        onValueChange = onChange,
        label = stringResource(label),
        enabled = enabled,
        singleLine = false,
        minLines = 3,
    )
}

@Composable
private fun CheckRow(checked: Boolean, label: Int, enabled: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = Reach.touch),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Spacing.tight),
    ) {
        Checkbox(checked = checked, onCheckedChange = onChange, enabled = enabled)
        Text(stringResource(label), style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun BatchButtons(editor: BatchEditorState, actions: BatchListingsActions) {
    if (editor.readOnly) return
    SecondaryButton(
        text = stringResource(R.string.hub_save),
        onClick = actions.onSave,
        enabled = editor.canSave,
        modifier = Modifier.fillMaxWidth().testTag(TAG_BATCH_SAVE),
    )
    if (editor.batch.status == ListingStatus.PUBLISHED.wire) {
        SecondaryButton(
            text = stringResource(R.string.hub_unpublish),
            onClick = actions.onUnpublish,
            enabled = editor.canUnpublish,
            modifier = Modifier.fillMaxWidth().testTag(TAG_BATCH_UNPUBLISH),
        )
    } else {
        PrimaryButton(
            text = stringResource(R.string.hub_publish),
            onClick = actions.onPublish,
            enabled = editor.canPublish,
            modifier = Modifier.fillMaxWidth().testTag(TAG_BATCH_PUBLISH),
        )
    }
}
