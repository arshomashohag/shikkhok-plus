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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.PrimaryButton
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SecondaryButton
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.ShikkhokTextField
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.designsystem.asHeading
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hublisting.HubChecklistItem
import com.shikkhokplus.app.feature.hublisting.HubDraft
import com.shikkhokplus.app.feature.hublisting.HubFailure
import com.shikkhokplus.app.feature.hublisting.HubLimits
import com.shikkhokplus.app.feature.hublisting.HubListingState
import com.shikkhokplus.app.feature.hublisting.HubListingUiState
import com.shikkhokplus.app.feature.hublisting.HubNotice
import com.shikkhokplus.app.feature.hublisting.ListingStatus
import com.shikkhokplus.app.feature.hublisting.OwnerListingResponse
import com.shikkhokplus.app.feature.hublisting.SlugNote
import com.shikkhokplus.app.feature.hublisting.TeachingMode
import kotlinx.coroutines.delay

/** The Save button. */
const val TAG_HUB_SAVE: String = "hub_save"

/** The Publish button. */
const val TAG_HUB_PUBLISH: String = "hub_publish"

/** The Unpublish button. */
const val TAG_HUB_UNPUBLISH: String = "hub_unpublish"

/** The retry control after a failed call. */
const val TAG_HUB_RETRY: String = "hub_retry"

/** The suspended banner. */
const val TAG_HUB_SUSPENDED: String = "hub_suspended"

/** The consent sheet's checkbox. */
const val TAG_HUB_AGREE: String = "hub_agree"

/** The consent sheet's confirm button. */
const val TAG_HUB_CONFIRM_PUBLISH: String = "hub_confirm_publish"

/** The street address field, shown to centres only. */
const val TAG_HUB_STREET: String = "hub_street"

/** The Runs classes badge. */
const val TAG_HUB_BADGE: String = "hub_badge"

/** How long a confirmation stays up. */
private const val NOTICE_MILLIS: Long = 3_000

/**
 * What the listing screen's controls call.
 *
 * @property onEdit Changes what is typed
 * @property onToggleMode Ticks or unticks a teaching mode
 * @property onPickDivision Chooses a division
 * @property onPickDistrict Chooses a district
 * @property onPickUpazila Chooses an upazila or a city corporation
 * @property onPickThana Chooses a thana of the city corporation, or empty for the whole city
 * @property onRetryAreas Reads the area lists again
 * @property onSave Sends what changed
 * @property onCheckSlug Asks whether the web address is free
 * @property onOpenPublish Opens the consent sheet
 * @property onClosePublish Closes it
 * @property onAgree Ticks or unticks its box
 * @property onPublish Publishes
 * @property onUnpublish Takes the listing down
 * @property onRetry Repeats what last failed
 * @property onDismissNotice Forgets the confirmation
 * @property onBatches Opens the batch listings
 * @property onAppeal Opens Help to appeal a suspension
 * @property onBack Leaves the screen
 */
data class HubListingActions(
    val onEdit: ((HubDraft) -> HubDraft) -> Unit = {},
    val onToggleMode: (TeachingMode, Boolean) -> Unit = { _, _ -> },
    val onPickDivision: (String) -> Unit = {},
    val onPickDistrict: (String) -> Unit = {},
    val onPickUpazila: (String) -> Unit = {},
    val onPickThana: (String) -> Unit = {},
    val onRetryAreas: () -> Unit = {},
    val onSave: () -> Unit = {},
    val onCheckSlug: () -> Unit = {},
    val onOpenPublish: () -> Unit = {},
    val onClosePublish: () -> Unit = {},
    val onAgree: (Boolean) -> Unit = {},
    val onPublish: () -> Unit = {},
    val onUnpublish: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onDismissNotice: () -> Unit = {},
    val onBatches: () -> Unit = {},
    val onAppeal: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The owner's public listing: the page parents find on ShikkhokPlus.
 *
 * It renders the server's decisions. The checklist and `publishable`
 * arrive computed and are all that enable Publish; a suspended listing is
 * read-only with how to appeal; a failed save keeps everything typed and
 * offers Retry [TC-8, TC-9].
 *
 * @param state What to render
 * @param actions What the controls call
 * @param modifier Layout modifier from the caller
 */
@Composable
fun HubListingScreen(
    state: HubListingState,
    actions: HubListingActions,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(title = stringResource(R.string.hub_title), modifier = modifier, onBack = actions.onBack) {
        when (val body = state.body) {
            HubListingUiState.Loading -> SkeletonList(rows = 4)
            is HubListingUiState.Error ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(body.messageKey)),
                    body = null,
                    retryLabel = if (body.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (body.retryable) actions.onRetry else null,
                )
            is HubListingUiState.Editing -> ListingBody(state, body.listing, body.checklist, readOnly = false, actions)
            is HubListingUiState.Suspended ->
                ListingBody(state, body.listing, body.listing.checklist, readOnly = true, actions)
        }
    }
    if (state.publishing) PublishSheet(state, actions)
}

@Composable
private fun ListingBody(
    state: HubListingState,
    listing: OwnerListingResponse,
    checklist: List<HubChecklistItem>,
    readOnly: Boolean,
    actions: HubListingActions,
) {
    state.notice?.let { notice ->
        LaunchedEffect(notice) {
            delay(NOTICE_MILLIS)
            actions.onDismissNotice()
        }
        Banner(title = stringResource(noticeText(notice)), tone = BannerTone.INFO)
    }
    StatusRow(ListingStatus.fromWire(listing.status), listing.runsClasses)
    if (readOnly) {
        Banner(
            title = stringResource(R.string.hub_suspended_title),
            body = stringResource(R.string.hub_suspended_body),
            tone = BannerTone.ERROR,
            modifier = Modifier.testTag(TAG_HUB_SUSPENDED),
            action = { TextAction(stringResource(R.string.hub_suspended_appeal), actions.onAppeal) },
        )
    }
    Text(
        stringResource(R.string.hub_checklist_title),
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.asHeading(),
    )
    ChecklistCard(checklist)
    ListingFields(state, readOnly, actions)
    state.failure?.let { FailureBanner(it, actions.onRetry) }
    if (!readOnly) ListingButtons(state, actions)
    if (!readOnly && state.dirty && listing.publishable) {
        Text(
            stringResource(R.string.hub_save_first),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    TextAction(stringResource(R.string.hub_batches_link), actions.onBatches, Modifier.fillMaxWidth())
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ListingFields(state: HubListingState, readOnly: Boolean, actions: HubListingActions) {
    val draft = state.draft
    val enabled = !readOnly
    ShikkhokTextField(
        value = draft.publicName,
        onValueChange = { v -> actions.onEdit { it.copy(publicName = v.take(HubLimits.PUBLIC_NAME)) } },
        label = stringResource(R.string.hub_field_public_name),
        enabled = enabled,
        singleLine = false,
    )
    ShikkhokTextField(
        value = draft.slug,
        onValueChange = { v -> actions.onEdit { it.copy(slug = v.take(HubLimits.SLUG)) } },
        label = stringResource(R.string.hub_field_slug),
        help = stringResource(R.string.hub_slug_help),
        error = if (state.slugNote == SlugNote.TAKEN) stringResource(R.string.hub_slug_taken_ui) else null,
        enabled = enabled,
    )
    state.slugNote?.takeIf { it == SlugNote.AVAILABLE }?.let {
        Text(stringResource(R.string.hub_slug_available), style = MaterialTheme.typography.bodyMedium)
    }
    TextAction(
        stringResource(R.string.hub_slug_check),
        actions.onCheckSlug,
        enabled = enabled && draft.slug.isNotBlank(),
    )
    LanguageFields(draft, enabled, actions.onEdit)
    ShikkhokTextField(
        value = draft.qualifications,
        onValueChange = { v -> actions.onEdit { it.copy(qualifications = v.take(HubLimits.QUALIFICATIONS)) } },
        label = stringResource(R.string.hub_field_qualifications),
        enabled = enabled,
        singleLine = false,
        minLines = 2,
    )
    Text(stringResource(R.string.hub_field_mode), style = MaterialTheme.typography.labelLarge)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
        TeachingMode.entries.forEach { mode ->
            val on = mode.wire in draft.modes
            FilterChip(
                selected = on,
                onClick = { actions.onToggleMode(mode, !on) },
                enabled = enabled,
                label = { Text(stringResource(modeLabel(mode.wire))) },
            )
        }
    }
    AreaPickers(state, enabled, actions)
    if (state.showStreet) {
        ShikkhokTextField(
            value = draft.streetAddress,
            onValueChange = { v -> actions.onEdit { it.copy(streetAddress = v.take(HubLimits.STREET)) } },
            label = stringResource(R.string.hub_field_street),
            enabled = enabled,
            singleLine = false,
            fieldModifier = Modifier.testTag(TAG_HUB_STREET),
        )
    }
    ShikkhokTextField(
        value = draft.phone,
        onValueChange = { v -> actions.onEdit { it.copy(phone = v.take(HubLimits.PHONE)) } },
        label = stringResource(R.string.hub_field_phone),
        help = stringResource(R.string.hub_phone_help),
        enabled = enabled,
        keyboardType = KeyboardType.Phone,
    )
}

/** Headline and biography, in an English tab and a Bangla tab. */
@Composable
private fun LanguageFields(draft: HubDraft, enabled: Boolean, onEdit: ((HubDraft) -> HubDraft) -> Unit) {
    var bangla by rememberSaveable { mutableStateOf(false) }
    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.tight)) {
        FilterChip(
            selected = !bangla,
            onClick = { bangla = false },
            label = { Text(stringResource(R.string.hub_tab_english)) },
        )
        FilterChip(
            selected = bangla,
            onClick = { bangla = true },
            label = { Text(stringResource(R.string.hub_tab_bangla)) },
        )
    }
    if (bangla) {
        ShikkhokTextField(
            value = draft.headlineBn,
            onValueChange = { v -> onEdit { it.copy(headlineBn = v.take(HubLimits.HEADLINE)) } },
            label = stringResource(R.string.hub_field_headline_bn),
            enabled = enabled,
            singleLine = false,
        )
        ShikkhokTextField(
            value = draft.bioBn,
            onValueChange = { v -> onEdit { it.copy(bioBn = v.take(HubLimits.BIO)) } },
            label = stringResource(R.string.hub_field_bio_bn),
            enabled = enabled,
            singleLine = false,
            minLines = 4,
        )
    } else {
        ShikkhokTextField(
            value = draft.headlineEn,
            onValueChange = { v -> onEdit { it.copy(headlineEn = v.take(HubLimits.HEADLINE)) } },
            label = stringResource(R.string.hub_field_headline_en),
            enabled = enabled,
            singleLine = false,
        )
        ShikkhokTextField(
            value = draft.bioEn,
            onValueChange = { v -> onEdit { it.copy(bioEn = v.take(HubLimits.BIO)) } },
            label = stringResource(R.string.hub_field_bio_en),
            enabled = enabled,
            singleLine = false,
            minLines = 4,
        )
    }
}

@Composable
private fun AreaPickers(state: HubListingState, enabled: Boolean, actions: HubListingActions) {
    val areas = state.areas
    if (areas.failed) {
        Banner(
            title = stringResource(R.string.hub_areas_failed),
            tone = BannerTone.ERROR,
            action = { TextAction(stringResource(R.string.auth_retry), actions.onRetryAreas) },
        )
    }
    AreaDropdown(
        label = stringResource(R.string.hub_field_division),
        value = areas.divisionCode,
        options = areas.divisions,
        enabled = enabled,
        onPick = actions.onPickDivision,
    )
    AreaDropdown(
        label = stringResource(R.string.hub_field_district),
        value = state.draft.districtCode,
        options = areas.districts,
        enabled = enabled && areas.divisionCode.isNotEmpty(),
        onPick = actions.onPickDistrict,
    )
    AreaDropdown(
        label = stringResource(R.string.hub_field_upazila),
        value = areas.cityCode.ifEmpty { state.draft.upazilaCode },
        options = areas.upazilas,
        enabled = enabled && state.draft.districtCode.isNotEmpty(),
        onPick = actions.onPickUpazila,
    )
    if (areas.cityCode.isNotEmpty()) {
        AreaDropdown(
            label = stringResource(R.string.hub_field_thana),
            value = state.draft.upazilaCode.takeIf { it != areas.cityCode }.orEmpty(),
            options = areas.thanas,
            enabled = enabled,
            onPick = actions.onPickThana,
            none = stringResource(R.string.hub_thana_whole_city),
        )
    }
}

@Composable
private fun ListingButtons(state: HubListingState, actions: HubListingActions) {
    SecondaryButton(
        text = stringResource(R.string.hub_save),
        onClick = actions.onSave,
        enabled = state.canSave,
        modifier = Modifier.fillMaxWidth().testTag(TAG_HUB_SAVE),
    )
    if ((state.body as? HubListingUiState.Editing)?.status == ListingStatus.PUBLISHED) {
        SecondaryButton(
            text = stringResource(R.string.hub_unpublish),
            onClick = actions.onUnpublish,
            enabled = state.canUnpublish,
            modifier = Modifier.fillMaxWidth().testTag(TAG_HUB_UNPUBLISH),
        )
    } else {
        PrimaryButton(
            text = stringResource(R.string.hub_publish),
            onClick = actions.onOpenPublish,
            enabled = state.canPublish,
            modifier = Modifier.fillMaxWidth().testTag(TAG_HUB_PUBLISH),
        )
    }
}

/**
 * The consent sheet a listing is published through: what becomes public,
 * that it can be unpublished at any time, and a box that must be ticked.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PublishSheet(state: HubListingState, actions: HubListingActions) {
    ModalBottomSheet(
        onDismissRequest = actions.onClosePublish,
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
            Text(
                stringResource(R.string.hub_publish_title),
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.asHeading(),
            )
            Text(stringResource(R.string.hub_publish_intro), style = MaterialTheme.typography.bodyMedium)
            listOf(
                R.string.hub_publish_item_profile,
                R.string.hub_publish_item_contact,
                R.string.hub_publish_item_batches,
            ).forEach { Text("• " + stringResource(it), style = MaterialTheme.typography.bodyMedium) }
            Text(stringResource(R.string.hub_publish_never), style = MaterialTheme.typography.bodyMedium)
            Text(stringResource(R.string.hub_publish_unpublish), style = MaterialTheme.typography.bodyMedium)
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Spacing.tight),
            ) {
                Checkbox(
                    checked = state.agreed,
                    onCheckedChange = actions.onAgree,
                    modifier = Modifier.testTag(TAG_HUB_AGREE),
                )
                Text(stringResource(R.string.hub_publish_agree), style = MaterialTheme.typography.bodyLarge)
            }
            state.failure?.let { FailureBanner(it, actions.onRetry) }
            PrimaryButton(
                text = stringResource(R.string.hub_publish_confirm),
                onClick = actions.onPublish,
                enabled = state.agreed && !state.saving,
                modifier = Modifier.fillMaxWidth().testTag(TAG_HUB_CONFIRM_PUBLISH),
            )
            SecondaryButton(
                text = stringResource(R.string.action_cancel),
                onClick = actions.onClosePublish,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

/** The server's checklist, each item with its state in words. */
@Composable
internal fun ChecklistCard(items: List<HubChecklistItem>) {
    ShikkhokCard {
        items.forEach { item ->
            Row(
                Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Spacing.tight),
            ) {
                Text(if (item.done) "✓" else "○", style = MaterialTheme.typography.titleMedium)
                Text(
                    checklistLabel(item.key)?.let { stringResource(it) } ?: item.key,
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    stringResource(if (item.done) R.string.hub_check_done else R.string.hub_check_todo),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/** A failure the server named, with Retry when repeating the call can help. */
@Composable
internal fun FailureBanner(failure: HubFailure, onRetry: () -> Unit) {
    val message = stringResource(MessageKeys.resolve(failure.messageKey))
    Banner(
        title = if (failure.saveFailed) stringResource(R.string.hub_save_failed) + " " + message else message,
        tone = BannerTone.ERROR,
        action =
            if (failure.canRetry) {
                { TextAction(stringResource(R.string.auth_retry), onRetry, Modifier.testTag(TAG_HUB_RETRY)) }
            } else {
                null
            },
    )
}

private fun noticeText(notice: HubNotice): Int =
    when (notice) {
        HubNotice.SAVED -> R.string.hub_saved
        HubNotice.PUBLISHED -> R.string.hub_published_snack
        HubNotice.UNPUBLISHED -> R.string.hub_unpublished
    }
