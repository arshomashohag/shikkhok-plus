package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.feature.hublisting.BatchListingsViewModel
import com.shikkhokplus.app.feature.hublisting.HttpHubApi
import com.shikkhokplus.app.feature.hublisting.HttpHubFeedbackApi
import com.shikkhokplus.app.feature.hublisting.HubFeedbackViewModel
import com.shikkhokplus.app.feature.hublisting.HubListingViewModel
import com.shikkhokplus.app.feature.hublisting.NameConsentViewModel
import com.shikkhokplus.app.feature.hublisting.ui.BatchListingsActions
import com.shikkhokplus.app.feature.hublisting.ui.BatchListingsScreen
import com.shikkhokplus.app.feature.hublisting.ui.HubFeedbackActions
import com.shikkhokplus.app.feature.hublisting.ui.HubFeedbackScreen
import com.shikkhokplus.app.feature.hublisting.ui.HubListingActions
import com.shikkhokplus.app.feature.hublisting.ui.HubListingScreen
import com.shikkhokplus.app.feature.hublisting.report.HttpHubReportApi
import com.shikkhokplus.app.feature.hublisting.report.HubReportViewModel
import com.shikkhokplus.app.feature.hublisting.report.ReportLink
import com.shikkhokplus.app.feature.hublisting.report.ui.HubReportActions
import com.shikkhokplus.app.feature.hublisting.report.ui.HubReportScreen
import com.shikkhokplus.app.feature.hublisting.ui.NameConsentScreen
import io.ktor.client.HttpClient

/**
 * The public hub's owner screens, pushed over More: the listing editor,
 * its batch listings, and a centre member's name consent; and the demand
 * question, opened from its inbox item; and, for any signed-in reader,
 * reporting a public hub page, opened from that page's App Link.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 */
internal fun NavGraphBuilder.hubRoutes(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(Destination.HubListing.route) {
        val model: HubListingViewModel = viewModel { HubListingViewModel(HttpHubApi(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        HubListingScreen(
            state = state,
            actions =
                HubListingActions(
                    onEdit = model::edit,
                    onToggleMode = model::toggleMode,
                    onPickDivision = model::pickDivision,
                    onPickDistrict = model::pickDistrict,
                    onPickUpazila = model::pickUpazila,
                    onPickThana = model::pickThana,
                    onRetryAreas = model::retryAreas,
                    onSave = model::save,
                    onCheckSlug = model::checkSlug,
                    onOpenPublish = model::openPublish,
                    onClosePublish = model::closePublish,
                    onAgree = model::agree,
                    onPublish = model::publish,
                    onUnpublish = model::unpublish,
                    onRetry = model::retry,
                    onDismissNotice = model::dismissNotice,
                    onBatches = { navController.navigate(Destination.BatchListings.route) },
                    // A suspended owner appeals by asking Help.
                    onAppeal = { navController.navigate(Destination.AskQuestion.route) },
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.BatchListings.route) {
        val model: BatchListingsViewModel = viewModel { BatchListingsViewModel(HttpHubApi(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        BatchListingsScreen(
            state = state,
            actions =
                BatchListingsActions(
                    onEdit = model::edit,
                    onClose = model::close,
                    onChange = model::change,
                    onSave = model::save,
                    onPublish = model::publish,
                    onUnpublish = model::unpublish,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.NameConsent.route) {
        val model: NameConsentViewModel = viewModel { NameConsentViewModel(HttpHubApi(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        NameConsentScreen(
            state = state,
            onSet = model::set,
            onRetry = model::retry,
            onRetryLoad = model::retryLoad,
            onBack = { navController.popBackStack() },
        )
    }

    composable(
        route = Destination.HubFeedback.route,
        arguments =
            listOf(
                navArgument(Destination.HubFeedback.ARG_OWNER) { type = NavType.StringType },
                navArgument(Destination.HubFeedback.ARG_DAY) { type = NavType.IntType },
            ),
    ) { entry ->
        val ownerId = entry.arguments?.getString(Destination.HubFeedback.ARG_OWNER).orEmpty()
        val day = entry.arguments?.getInt(Destination.HubFeedback.ARG_DAY) ?: 0
        val model: HubFeedbackViewModel =
            viewModel(key = "$ownerId/$day") { HubFeedbackViewModel(HttpHubFeedbackApi(client), ownerId, day) }
        val state by model.state.collectAsState()
        HubFeedbackScreen(
            state = state,
            actions =
                HubFeedbackActions(
                    onAnswer = model::answer,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(
        route = Destination.HubReport.route,
        arguments =
            listOf(
                navArgument(Destination.HubReport.ARG_KIND) {
                    type = NavType.StringType
                    defaultValue = ""
                },
                navArgument(Destination.HubReport.ARG_ID) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
    ) { entry ->
        val kind = entry.arguments?.getString(Destination.HubReport.ARG_KIND)
        val id = entry.arguments?.getString(Destination.HubReport.ARG_ID)
        val model: HubReportViewModel =
            viewModel(key = "hub-report/$kind/$id") {
                HubReportViewModel(HttpHubReportApi(client), ReportLink(kind, id))
            }
        val state by model.state.collectAsState()
        HubReportScreen(
            state = state,
            actions =
                HubReportActions(
                    onReason = model::pickReason,
                    onNote = model::editNote,
                    onSend = model::send,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}

/**
 * Opens the report screen for a "Report this page" App Link, once there
 * is someone to report as.
 *
 * **Signed out, the link waits**: the graph starts at sign-in, and the
 * link stays pending in `MainActivity` (kept across a rotation in its
 * saved state) until the session is signed in and the graph is rebuilt
 * for it -- which is also after the choose-username gate and the lens
 * picker, since neither composes the graph. Then the screen is pushed
 * over the new home, so Back lands there, and the link is consumed so it
 * cannot open twice. The same shape as the inbox notification's
 * `OpenInboxEffect`.
 *
 * @param navController The app's controller
 * @param signedIn Whether a session exists
 * @param link The link waiting to be opened, or null
 * @param onOpened Called once the screen has been opened, to consume the link
 */
@Composable
internal fun HubReportLinkEffect(
    navController: NavController,
    signedIn: Boolean,
    link: ReportLink?,
    onOpened: () -> Unit,
) {
    LaunchedEffect(signedIn, link) {
        if (signedIn && link != null) {
            navController.navigate(Destination.HubReport.of(link.kind, link.id)) { launchSingleTop = true }
            onOpened()
        }
    }
}
