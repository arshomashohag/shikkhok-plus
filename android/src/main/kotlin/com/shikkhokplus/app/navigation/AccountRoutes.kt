package com.shikkhokplus.app.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.navArgument
import com.shikkhokplus.app.core.model.IdentifierKind
import com.shikkhokplus.app.core.network.HttpAccountRepository
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.feature.account.AddContactUiState
import com.shikkhokplus.app.feature.account.AddContactViewModel
import com.shikkhokplus.app.feature.account.PasswordChangeUiState
import com.shikkhokplus.app.feature.account.PasswordChangeViewModel
import com.shikkhokplus.app.feature.account.ui.AddContactScreen
import com.shikkhokplus.app.feature.account.ui.PasswordChangeScreen
import com.shikkhokplus.app.feature.account.ui.PasswordPrompt
import com.shikkhokplus.app.feature.profile.ui.MoreActions
import com.shikkhokplus.app.feature.profile.ProfileSummary
import io.ktor.client.HttpClient

/**
 * The account's own sign-in settings, pushed over More for every lens:
 * the password, and adding a phone or an email.
 *
 * Their own file for the reason the other route groups have one.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 * @param session The session, for the token store, the prompt and the
 *   lens re-read a new phone number can cause
 */
internal fun NavGraphBuilder.accountRoutes(
    client: HttpClient,
    navController: NavHostController,
    session: SessionBinding,
) {
    val tokens: TokenStore = session.tokens ?: return

    composable(
        Destination.SetPassword.route,
        arguments =
            listOf(
                navArgument(Destination.SetPassword.ARG_HAS) {
                    type = NavType.BoolType
                    defaultValue = true
                },
            ),
    ) { entry ->
        // Whether a current password is asked for is the server's answer,
        // carried by whoever opened the screen: the prompt is shown only
        // for an account without one, and More passes what it last read.
        val hasPassword = entry.arguments?.getBoolean(Destination.SetPassword.ARG_HAS) ?: true
        val model: PasswordChangeViewModel =
            viewModel { PasswordChangeViewModel(HttpAccountRepository(client, tokens), hasPassword) }
        val state by model.state.collectAsState()

        LaunchedEffect(state) {
            if (state == PasswordChangeUiState.Done) {
                session.onPasswordSet()
                navController.popBackStack()
            }
        }

        PasswordChangeScreen(
            state = state,
            onSubmit = model::submit,
            onBack = { navController.popBackStack() },
        )
    }

    composable(Destination.AddContact.route) { entry ->
        val kind =
            if (entry.arguments?.getString(Destination.AddContact.ARG_KIND) == "email") {
                IdentifierKind.EMAIL
            } else {
                IdentifierKind.PHONE
            }
        val model: AddContactViewModel =
            viewModel { AddContactViewModel(HttpAccountRepository(client, tokens), kind) }
        val state by model.state.collectAsState()

        // **A new phone can bring seats with it**: the server links the
        // seats and centre invitations teachers recorded for that number,
        // so the lenses are re-read, quietly, and More re-reads the
        // account when it is shown again.
        LaunchedEffect(state) {
            if (state is AddContactUiState.Added) {
                session.onLensesChanged()
                navController.popBackStack()
            }
        }

        AddContactScreen(
            state = state,
            onRequestCode = model::requestCode,
            onSubmitCode = model::submitCode,
            onResend = model::resendCode,
            onChange = model::changeValue,
            onBack = { navController.popBackStack() },
        )
    }
}

/**
 * The account rows of More that depend on what the account holds.
 *
 * **Decided here, from the server's answer, so More's composable decides
 * nothing**: "Add phone number" only for an account with no number, "Add
 * email" only for one with no email, and the password row always, its
 * title chosen by `has_password`. With nothing read yet, no add row is
 * offered: an unknown is not an absence.
 *
 * Internal so a test can hold each case to its rows.
 *
 * @param summary The last profile the server confirmed, or null
 * @param navigate Opens a route
 * @return The password row's action, and the two add rows' actions or null
 */
internal fun accountRowsFor(
    summary: ProfileSummary?,
    navigate: (String) -> Unit,
): AccountRows =
    AccountRows(
        onPassword = { navigate(Destination.SetPassword.of(summary?.hasPassword ?: true)) },
        hasPassword = summary?.hasPassword ?: true,
        onAddPhone =
            { navigate(Destination.AddContact.of(IdentifierKind.PHONE)) }
                .takeIf { summary != null && summary.phone == null },
        onAddEmail =
            { navigate(Destination.AddContact.of(IdentifierKind.EMAIL)) }
                .takeIf { summary != null && summary.email == null },
    )

/**
 * The account rows of More that depend on what the account holds.
 *
 * @property onPassword Opens the password screen
 * @property hasPassword Whether the row reads "Change password" or "Set a password"
 * @property onAddPhone Opens "Add phone number", or null
 * @property onAddEmail Opens "Add email", or null
 */
internal data class AccountRows(
    val onPassword: () -> Unit,
    val hasPassword: Boolean,
    val onAddPhone: (() -> Unit)?,
    val onAddEmail: (() -> Unit)?,
)


/**
 * Add the account rows to More's rows.
 *
 * @param rows The rows to add, or null where the password screens are not
 *   routed (a test with no token store)
 * @return The same rows with the sign-in rows set
 */
internal fun MoreActions.withAccountRows(rows: AccountRows?): MoreActions =
    if (rows == null) {
        this
    } else {
        copy(
            onPassword = rows.onPassword,
            hasPassword = rows.hasPassword,
            onAddPhone = rows.onAddPhone,
            onAddEmail = rows.onAddEmail,
        )
    }

/**
 * The app's graph, with the persistent prompt to set a password above it
 * where it belongs: on the lens's home screen and on More, for an account
 * the server says has none. Nowhere else, so it never sits over a class
 * being marked.
 *
 * Above the graph rather than inside each home, so every lens's home
 * shows the same card.
 *
 * @param signedIn Whether anyone is signed in
 * @param missing Whether the account has no password, as `GET /v1/me` said
 * @param lens The lens in use, whose home shows the prompt
 * @param navController The app's controller
 * @param content The graph
 */
@Composable
internal fun PasswordPromptFrame(
    signedIn: Boolean,
    missing: Boolean,
    lens: Lens?,
    navController: NavHostController,
    content: @Composable () -> Unit,
) {
    val route = navController.currentBackStackEntryAsState().value?.destination?.route
    val here = route == homeFor(lens) || route == Destination.Profile.route
    Column(Modifier.fillMaxSize()) {
        if (signedIn && missing && here) {
            PasswordPrompt(onSetPassword = { navController.navigate(Destination.SetPassword.of(false)) })
        }
        Box(Modifier.weight(1f)) { content() }
    }
}
