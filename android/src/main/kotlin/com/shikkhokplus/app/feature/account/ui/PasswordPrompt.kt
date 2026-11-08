package com.shikkhokplus.app.feature.account.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.TextAction

/** The persistent prompt to set a password. */
const val TAG_PASSWORD_PROMPT: String = "account_password_prompt"

/** Its action. */
const val TAG_PASSWORD_PROMPT_ACTION: String = "account_password_prompt_action"

/**
 * "Set a password so you can sign in without a code."
 *
 * **Persistent, not dismissable.** An account from before passwords has
 * none, and from now on a code is only for recovery; until it sets one,
 * every sign-in on a new phone costs a code. The card stays on the home
 * screen and on More until the server says the account has a password.
 * Whether to show it is the caller's, from the server's `has_password`.
 *
 * @param onSetPassword Called from the card's action
 * @param modifier The layout modifier
 */
@Composable
fun PasswordPrompt(
    onSetPassword: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Banner(
        title = stringResource(R.string.account_password_prompt_title),
        body = stringResource(R.string.account_password_prompt_body),
        tone = BannerTone.INFO,
        action = {
            TextAction(
                text = stringResource(R.string.account_password_prompt_action),
                onClick = onSetPassword,
                modifier = Modifier.testTag(TAG_PASSWORD_PROMPT_ACTION),
            )
        },
        modifier = modifier.padding(horizontal = 16.dp, vertical = 8.dp).testTag(TAG_PASSWORD_PROMPT),
    )
}
