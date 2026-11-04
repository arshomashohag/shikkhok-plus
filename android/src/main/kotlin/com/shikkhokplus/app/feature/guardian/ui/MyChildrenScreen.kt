package com.shikkhokplus.app.feature.guardian.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.MenuCard
import com.shikkhokplus.app.core.designsystem.MenuDivider
import com.shikkhokplus.app.core.designsystem.MenuRow
import com.shikkhokplus.app.core.designsystem.MenuTrailing
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.Spacing
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.guardian.ChildCard
import com.shikkhokplus.app.feature.guardian.GuardianUiState

/** One child's row on My children. */
const val TAG_MY_CHILD_ROW: String = "my_child_row"

/** The "A child is missing?" card. */
const val TAG_MY_CHILDREN_MISSING: String = "my_children_missing"

/**
 * My children (G4), opened from the guardian's More.
 *
 * **A list to read, not to manage.** A child appears here because a
 * teacher added this guardian's number to that child's seat; a guardian
 * cannot add or remove one, and the screen says so, with what to do
 * when a child is missing. Choosing which child to look at stays on
 * the home screen's switcher [BR4.2], so tapping a row selects that
 * child there and goes back.
 *
 * @param state The guardian's children, as the home screen reads them
 * @param phone This guardian's number, for the "missing" note, or null
 * @param onBack Called by the back arrow
 * @param onChild Called with a child's position to show that child
 * @param onRetry Called when a retryable failure offers a retry
 * @param modifier Layout modifier from the caller
 */
@Composable
fun MyChildrenScreen(
    state: GuardianUiState,
    phone: String?,
    onBack: () -> Unit,
    onChild: (Int) -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    ScreenScaffold(
        title = stringResource(R.string.my_children_title),
        modifier = modifier,
        onBack = onBack,
    ) {
        when (state) {
            GuardianUiState.Idle, GuardianUiState.Loading -> SkeletonList(rows = 2)
            is GuardianUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.dues_retry) else null,
                    onRetry = if (state.retryable) onRetry else null,
                )
            is GuardianUiState.Loaded -> ChildList(state.children, onChild)
            is GuardianUiState.Empty -> Unit
        }
        Text(
            text = stringResource(R.string.my_children_note),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        MissingChildCard(phone)
    }
}

/**
 * The children, one row each.
 *
 * @param children Every child linked to this guardian
 * @param onChild Called with the tapped child's position
 */
@Composable
private fun ChildList(children: List<ChildCard>, onChild: (Int) -> Unit) {
    MenuCard {
        children.forEachIndexed { index, child ->
            if (index > 0) MenuDivider()
            MenuRow(
                title = Numerals.freeText(child.name),
                subtitle = batchCount(child.batchCount),
                trailing = MenuTrailing.Chevron,
                leading = { ChildAvatar(child.name) },
                onClick = { onChild(index) },
                modifier = Modifier.testTag(TAG_MY_CHILD_ROW),
            )
        }
    }
}

/**
 * "A child is missing?": who to ask, and with which number.
 *
 * @param phone This guardian's number, or null when it is not known
 */
@Composable
private fun MissingChildCard(phone: String?) {
    Column(
        modifier =
            Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface, MaterialTheme.shapes.medium)
                .padding(horizontal = Spacing.screen, vertical = 14.dp)
                .testTag(TAG_MY_CHILDREN_MISSING),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(
            text = stringResource(R.string.my_children_missing_title),
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            text =
                phone?.let { stringResource(R.string.my_children_missing_body, Numerals.phone(it)) }
                    ?: stringResource(R.string.my_children_missing_body_plain),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * A child's first letter in a grey circle, the design's `.kid`.
 *
 * @param name The child's name
 * @param modifier The layout modifier
 */
@Composable
private fun ChildAvatar(name: String, modifier: Modifier = Modifier) {
    Box(
        modifier =
            modifier
                .size(44.dp)
                .background(MaterialTheme.colorScheme.surfaceContainerHigh, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = name.trim().take(1).uppercase(),
            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/**
 * "1 batch" or "3 batches".
 *
 * @param count How many batches the child is in
 * @return The label
 */
@Composable
private fun batchCount(count: Int): String =
    if (count == 1) {
        stringResource(R.string.guardian_one_batch)
    } else {
        stringResource(R.string.guardian_batch_count, Numerals.count(count))
    }
