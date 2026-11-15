package com.shikkhokplus.app.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.shikkhokplus.app.core.network.HttpProfileRepository
import com.shikkhokplus.app.feature.account.ContactCard
import com.shikkhokplus.app.feature.account.ContactsViewModel
import com.shikkhokplus.app.feature.account.RemoveContactViewModel
import com.shikkhokplus.app.feature.account.ReplaceContactUiState
import com.shikkhokplus.app.feature.account.ReplaceContactViewModel
import com.shikkhokplus.app.feature.account.UsernameViewModel
import com.shikkhokplus.app.feature.account.ui.ContactsActions
import com.shikkhokplus.app.feature.account.ui.ContactsScreen
import com.shikkhokplus.app.feature.account.ui.RemoveContactActions
import com.shikkhokplus.app.feature.account.ui.RemoveContactSheet
import com.shikkhokplus.app.feature.account.ui.ReplaceContactActions
import com.shikkhokplus.app.feature.account.ui.ReplaceContactScreen
import com.shikkhokplus.app.feature.account.ui.UsernameActions
import com.shikkhokplus.app.feature.account.ui.UsernameScreen
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

    usernameRoute(client, navController, session, tokens)
    contactsRoutes(client, navController, session, tokens)
}

/**
 * The Username screen [W5]: the stored name, and renaming it.
 *
 * A rename ends no session [FR7.5]; afterwards the account is re-read
 * quietly, so the More row shows the new name when More is shown again.
 */
private fun NavGraphBuilder.usernameRoute(
    client: HttpClient,
    navController: NavHostController,
    session: SessionBinding,
    tokens: TokenStore,
) {
    composable(Destination.Username.route) {
        val model: UsernameViewModel =
            viewModel {
                UsernameViewModel(
                    repository = HttpAccountRepository(client, tokens),
                    profile = HttpProfileRepository(client),
                    onChanged = session.onLensesChanged,
                )
            }
        val state by model.state.collectAsState()
        val hint by model.availability.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        UsernameScreen(
            state = state,
            availability = hint,
            actions =
                UsernameActions(
                    onChange = model::startChange,
                    onCancel = model::cancel,
                    onEdited = model::edited,
                    onSave = model::save,
                    onSetPassword = { navController.navigate(Destination.SetPassword.of(false)) },
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}

/**
 * Contacts [W6]: the two cards, the remove sheet over them, and the
 * replace flow pushed over them.
 *
 * **Every finish re-reads**: Contacts reads the account each time it is
 * shown and after a removal, and a replacement or a removal also re-reads
 * the lenses quietly, because a new phone or email can link seats [FR6.5].
 */
private fun NavGraphBuilder.contactsRoutes(
    client: HttpClient,
    navController: NavHostController,
    session: SessionBinding,
    tokens: TokenStore,
) {
    composable(Destination.Contacts.route) {
        val model: ContactsViewModel = viewModel { ContactsViewModel(HttpProfileRepository(client)) }
        val state by model.state.collectAsState()
        var removing by remember { mutableStateOf<ContactCard?>(null) }
        // Each opening of the sheet is a fresh question with its own ViewModel.
        var opened by remember { mutableIntStateOf(0) }
        // Read on every visit, so a return from Add or Replace shows the server's answer.
        LaunchedEffect(Unit) { model.load() }
        ContactsScreen(
            state = state,
            actions =
                ContactsActions(
                    onAdd = { navController.navigate(Destination.AddContact.of(it)) },
                    onReplace = { navController.navigate(Destination.ReplaceContact.of(it)) },
                    onRemove = {
                        opened++
                        removing = it
                    },
                    onSetPassword = { navController.navigate(Destination.SetPassword.of(false)) },
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
        removing?.let { card ->
            val contact = card.contact ?: return@let
            val remover: RemoveContactViewModel =
                viewModel(key = "remove-${card.kind}-$opened") {
                    RemoveContactViewModel(HttpAccountRepository(client, tokens), card.kind, contact)
                }
            val removeState by remover.state.collectAsState()
            RemoveContactSheet(
                state = removeState,
                actions =
                    RemoveContactActions(
                        onRemove = remover::remove,
                        onAddOther = {
                            removing = null
                            navController.navigate(Destination.AddContact.of(card.kind.other()))
                        },
                        onSetPassword = {
                            removing = null
                            navController.navigate(Destination.SetPassword.of(false))
                        },
                        onRemoved = {
                            removing = null
                            session.onLensesChanged()
                            model.load(removedKind = card.kind)
                        },
                        onDismiss = { removing = null },
                    ),
            )
        }
    }

    composable(
        Destination.ReplaceContact.route,
        arguments =
            listOf(
                navArgument(Destination.ReplaceContact.ARG_KIND) {
                    type = NavType.StringType
                    defaultValue = "phone"
                },
            ),
    ) { entry ->
        val kind =
            if (entry.arguments?.getString(Destination.ReplaceContact.ARG_KIND) == "email") {
                IdentifierKind.EMAIL
            } else {
                IdentifierKind.PHONE
            }
        val model: ReplaceContactViewModel =
            viewModel { ReplaceContactViewModel(HttpAccountRepository(client, tokens), kind) }
        val state by model.state.collectAsState()
        LaunchedEffect(state) {
            if (state is ReplaceContactUiState.Replaced) {
                // The new value may link seats; Contacts re-reads when shown.
                session.onLensesChanged()
                navController.popBackStack()
            }
        }
        ReplaceContactScreen(
            state = state,
            actions =
                ReplaceContactActions(
                    onRequestCode = model::requestCode,
                    onSubmitCode = model::submitCode,
                    onChange = model::changeValue,
                    onSetPassword = { navController.navigate(Destination.SetPassword.of(false)) },
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}

/** The other kind of contact. */
private fun IdentifierKind.other(): IdentifierKind =
    if (this == IdentifierKind.PHONE) IdentifierKind.EMAIL else IdentifierKind.PHONE

/**
 * The account rows of More that depend on what the account holds.
 *
 * **Decided here, from the server's answer, so More's composable decides
 * nothing**: the password row always, its title chosen by
 * `has_password`; the Username row always, its subtitle the stored name
 * (or none, which reads "Choose a username"); and one "Phone and email"
 * row, its subtitle the present contacts on one line, phone first [W5,
 * W6, Q3]. Adding, replacing and removing live on that row's screen.
 *
 * Internal so a test can hold each case to its rows.
 *
 * @param summary The last profile the server confirmed, or null
 * @param navigate Opens a route
 * @return The rows' actions and subtitles
 */
internal fun accountRowsFor(
    summary: ProfileSummary?,
    navigate: (String) -> Unit,
): AccountRows =
    AccountRows(
        onPassword = { navigate(Destination.SetPassword.of(summary?.hasPassword ?: true)) },
        hasPassword = summary?.hasPassword ?: true,
        onUsername = { navigate(Destination.Username.route) },
        username = summary?.username,
        onContacts = { navigate(Destination.Contacts.route) },
        contactsLine = summary?.let { listOfNotNull(it.phone, it.email).joinToString(" · ").ifEmpty { null } },
    )

/**
 * The account rows of More that depend on what the account holds.
 *
 * @property onPassword Opens the password screen
 * @property hasPassword Whether the row reads "Change password" or "Set a password"
 * @property onUsername Opens the Username screen
 * @property username The stored username for the row's subtitle, or null
 * @property onContacts Opens Phone and email
 * @property contactsLine The present contacts on one line, phone first, or null
 */
internal data class AccountRows(
    val onPassword: () -> Unit,
    val hasPassword: Boolean,
    val onUsername: () -> Unit,
    val username: String?,
    val onContacts: () -> Unit,
    val contactsLine: String?,
) {
    // The owner's own name and contacts [NFR3.2].
    override fun toString(): String = "AccountRows(hasPassword=$hasPassword, username=***, contactsLine=***)"
}


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
            onUsername = rows.onUsername,
            username = rows.username,
            onContacts = rows.onContacts,
            contactsLine = rows.contactsLine,
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
