package com.shikkhokplus.app.feature.account.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.ErrorCard
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.designsystem.ShikkhokCard
import com.shikkhokplus.app.core.designsystem.SkeletonList
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.feature.account.ContactCard
import com.shikkhokplus.app.feature.account.ContactsUiState
import com.shikkhokplus.app.feature.auth.MessageKeys

/** One contact card; the kind is in [contactCardTag]. */
const val TAG_CONTACTS_PASSWORD_NOTE: String = "contacts_password_note"

/** The Removed note on a card. */
const val TAG_CONTACTS_REMOVED: String = "contacts_removed"

/**
 * A card's test tag.
 *
 * @param kind Its kind
 * @return The tag
 */
fun contactCardTag(kind: IdentifierKind): String = "contacts_card_${kind.name.lowercase()}"

/**
 * An action's test tag on a card.
 *
 * @param kind The card's kind
 * @param action `add`, `replace` or `remove`
 * @return The tag
 */
fun contactActionTag(kind: IdentifierKind, action: String): String = "contacts_${action}_${kind.name.lowercase()}"

/**
 * What the Contacts screen can ask for.
 *
 * @property onAdd Adds a contact of a kind the account lacks
 * @property onReplace Replaces a contact
 * @property onRemove Asks to remove a contact
 * @property onSetPassword Opens setting a password
 * @property onRetry Reads again after a failure
 * @property onBack Leaves the screen
 */
data class ContactsActions(
    val onAdd: (IdentifierKind) -> Unit = {},
    val onReplace: (IdentifierKind) -> Unit = {},
    val onRemove: (ContactCard) -> Unit = {},
    val onSetPassword: () -> Unit = {},
    val onRetry: () -> Unit = {},
    val onBack: () -> Unit = {},
)

/**
 * The account's phone and email [W6, FR8.1]: one card each.
 *
 * **Renders the server's answer and decides nothing.** A present
 * contact always offers Replace and Remove, the only one included
 * [NFR3.11]; whether it may go is the server's to say. Without a
 * password a note says one is needed, and the actions stay enabled.
 *
 * @param state What to render
 * @param actions What the controls call
 */
@Composable
fun ContactsScreen(state: ContactsUiState, actions: ContactsActions) {
    ScreenScaffold(title = stringResource(R.string.contacts_title), onBack = actions.onBack) {
        when (state) {
            ContactsUiState.Loading -> SkeletonList(rows = 2)
            is ContactsUiState.Failed ->
                ErrorCard(
                    title = stringResource(MessageKeys.resolve(state.messageKey)),
                    body = null,
                    retryLabel = if (state.retryable) stringResource(R.string.auth_retry) else null,
                    onRetry = if (state.retryable) actions.onRetry else null,
                )
            is ContactsUiState.Loaded -> {
                if (state.passwordNote) {
                    Banner(
                        title = stringResource(R.string.contacts_password_note),
                        tone = BannerTone.INFO,
                        action = { TextAction(stringResource(R.string.contacts_set_password), actions.onSetPassword) },
                        modifier = Modifier.testTag(TAG_CONTACTS_PASSWORD_NOTE),
                    )
                }
                Card(state.phone, state.removedKind == IdentifierKind.PHONE, actions)
                Card(state.email, state.removedKind == IdentifierKind.EMAIL, actions)
            }
        }
    }
}

/**
 * One contact: its value with Replace and Remove, or Add.
 *
 * @param card The card
 * @param removed Whether it was just removed, for the note
 * @param actions What the controls call
 */
@Composable
private fun Card(card: ContactCard, removed: Boolean, actions: ContactsActions) {
    val phone = card.kind == IdentifierKind.PHONE
    ShikkhokCard(modifier = Modifier.testTag(contactCardTag(card.kind))) {
        Text(
            text = stringResource(if (phone) R.string.contacts_phone else R.string.contacts_email),
            style = MaterialTheme.typography.labelLarge,
        )
        val contact = card.contact
        if (contact != null) {
            Text(text = contact, style = MaterialTheme.typography.titleMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                TextAction(
                    text = stringResource(R.string.contacts_replace),
                    onClick = { actions.onReplace(card.kind) },
                    modifier = Modifier.testTag(contactActionTag(card.kind, "replace")),
                )
                TextAction(
                    text = stringResource(R.string.contacts_remove),
                    onClick = { actions.onRemove(card) },
                    modifier = Modifier.testTag(contactActionTag(card.kind, "remove")),
                )
            }
        } else {
            Text(
                text = stringResource(if (phone) R.string.contacts_no_phone else R.string.contacts_no_email),
                style = MaterialTheme.typography.bodyMedium,
            )
            if (removed) {
                Text(
                    text = stringResource(R.string.contacts_removed),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.testTag(TAG_CONTACTS_REMOVED),
                )
            }
            if (phone) {
                // Why a phone matters: teachers find students and guardians by number.
                Text(
                    text = stringResource(R.string.account_add_phone_body),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            TextAction(
                text = stringResource(if (phone) R.string.more_add_phone else R.string.more_add_email),
                onClick = { actions.onAdd(card.kind) },
                modifier = Modifier.fillMaxWidth().testTag(contactActionTag(card.kind, "add")),
            )
        }
    }
}
