package com.shikkhokplus.app.navigation

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.feature.hublisting.BatchListingsViewModel
import com.shikkhokplus.app.feature.hublisting.HttpHubApi
import com.shikkhokplus.app.feature.hublisting.HubListingViewModel
import com.shikkhokplus.app.feature.hublisting.NameConsentViewModel
import com.shikkhokplus.app.feature.hublisting.ui.BatchListingsActions
import com.shikkhokplus.app.feature.hublisting.ui.BatchListingsScreen
import com.shikkhokplus.app.feature.hublisting.ui.HubListingActions
import com.shikkhokplus.app.feature.hublisting.ui.HubListingScreen
import com.shikkhokplus.app.feature.hublisting.ui.NameConsentScreen
import io.ktor.client.HttpClient

/**
 * The public hub's owner screens, pushed over More: the listing editor,
 * its batch listings, and a centre member's name consent.
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
}
