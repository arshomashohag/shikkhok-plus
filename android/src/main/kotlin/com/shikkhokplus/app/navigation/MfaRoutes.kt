package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.core.network.HttpMfaRepository
import com.shikkhokplus.app.feature.mfa.MfaPrompt
import com.shikkhokplus.app.feature.mfa.MfaPromptStore
import com.shikkhokplus.app.feature.mfa.MfaStatusHolder
import com.shikkhokplus.app.feature.mfa.MfaViewModel
import com.shikkhokplus.app.feature.mfa.ui.MfaOfferSheet
import com.shikkhokplus.app.feature.mfa.ui.TwoStepActions
import com.shikkhokplus.app.feature.mfa.ui.TwoStepScreen
import com.shikkhokplus.app.feature.mfa.ui.openAuthenticator
import io.ktor.client.HttpClient

/**
 * Two-step verification [0028], pushed over More for every lens.
 *
 * The account's own setting, so the route is the same for every lens
 * and needs no workspace.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 * @param status Where each status read is shared with More, or null
 */
internal fun NavGraphBuilder.mfaRoutes(
    client: HttpClient,
    navController: NavHostController,
    status: MfaStatusHolder?,
) {
    composable(Destination.TwoStep.route) {
        val model: MfaViewModel = viewModel { MfaViewModel(HttpMfaRepository(client), status) }
        val state by model.state.collectAsState()
        val context = LocalContext.current

        LaunchedEffect(Unit) { model.load() }

        TwoStepScreen(
            state = state,
            actions =
                TwoStepActions(
                    onBack = { navController.popBackStack() },
                    onRetry = model::retry,
                    onTurnOn = model::turnOn,
                    onType = model::type,
                    // **No app is a message, not a crash.** The intent is
                    // implicit and nothing guarantees an authenticator is
                    // installed; the setup key stays on screen to type in.
                    onOpenAuthenticator = { uri ->
                        if (!openAuthenticator(context, uri)) model.noAuthenticatorApp()
                    },
                    onConfirm = model::confirm,
                    onStartTurnOff = model::startTurnOff,
                    onToggleRecovery = model::toggleRecoveryCode,
                    onTurnOff = model::turnOff,
                    onStartNewCodes = model::startNewCodes,
                    onRenew = model::renewCodes,
                    onFinishCodes = model::finishCodes,
                    onCancel = model::cancel,
                ),
        )
    }
}

/**
 * The one-time offer to turn on two-step verification, over whatever
 * home the session opened on.
 *
 * **Composed once per session**, inside the graph's session key, so a
 * new sign-in reads the status afresh and an earlier account's answer
 * never carries over. The read happens whatever the lens -- it is what
 * More's "Recommended" mark is drawn from -- but only an account the
 * server recommends it for, with it off and the offer unanswered on
 * this phone, is shown the sheet.
 *
 * @param active Whether someone is signed in; nothing is read otherwise
 * @param client The authenticated HTTP client
 * @param navController The app's controller, for Turn on
 * @param status Where the status read is shared with More
 * @param store Remembers which accounts answered
 * @param account The signed-in account, read when needed
 */
@Composable
internal fun MfaOffer(
    active: Boolean,
    client: HttpClient,
    navController: NavHostController,
    status: MfaStatusHolder,
    store: MfaPromptStore,
    account: () -> String?,
) {
    if (!active) return
    val prompt = remember { MfaPrompt(HttpMfaRepository(client), store, status, account) }
    var showing by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { showing = prompt.check() }

    if (showing) {
        MfaOfferSheet(
            onTurnOn = {
                prompt.answer()
                showing = false
                navController.navigate(Destination.TwoStep.route)
            },
            onNotNow = {
                prompt.answer()
                showing = false
            },
        )
    }
}
