package com.shikkhokplus.app.navigation

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.core.network.HttpPayRepository
import com.shikkhokplus.app.core.network.HttpGuardianRepository
import com.shikkhokplus.app.feature.guardian.PaymentsViewModel
import com.shikkhokplus.app.feature.guardian.ui.PaymentsScreen
import com.shikkhokplus.app.feature.pay.PayViewModel
import com.shikkhokplus.app.feature.student.FamilyReader
import com.shikkhokplus.app.feature.pay.ui.PayActions
import com.shikkhokplus.app.feature.pay.ui.PayScreen
import com.shikkhokplus.app.core.offline.LocalOfflineCopies
import com.shikkhokplus.app.core.offline.OfflineGuardianRepository
import com.shikkhokplus.app.core.offline.keptBy
import com.shikkhokplus.app.feature.dashboard.DashboardReader
import com.shikkhokplus.app.feature.guardian.GuardianViewModel
import com.shikkhokplus.app.feature.guardian.ui.GuardianActions
import com.shikkhokplus.app.feature.guardian.ui.GuardianHomeScreen
import com.shikkhokplus.app.feature.hubreviews.HttpHubReviewsApi
import com.shikkhokplus.app.feature.hubreviews.MyReviewsViewModel
import com.shikkhokplus.app.feature.hubreviews.showsEntry
import io.ktor.client.HttpClient

/**
 * G1, the guardian's home, one child at a time.
 *
 * Its own function rather than inline in the host, so a route test can
 * drive it: the home's Reviews row [H4] is drawn only once
 * `GET /v1/hub/reviewable` has answered with at least one batch, and
 * opens [Destination.HubMyReviews]. Reviews are by batch, not by child,
 * so the row is the same under every child.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.guardianHomeRoute(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(Destination.GuardianHome.route) {
        val copies = LocalOfflineCopies.current
        val model: GuardianViewModel =
            viewModel {
                val network = HttpGuardianRepository(client)
                GuardianViewModel(network.keptBy(copies, ::OfflineGuardianRepository))
            }
        val state by model.state.collectAsState()
        val refreshing by model.refreshing.collectAsState()
        val reviews: MyReviewsViewModel =
            viewModel(key = "guardian-reviews-entry") { MyReviewsViewModel(HttpHubReviewsApi(client)) }
        val reviewsState by reviews.state.collectAsState()

        LaunchedEffect(Unit) {
            model.load()
            reviews.load()
        }

        GuardianHomeScreen(
            state = state,
            // **Selection, not navigation** [BR4.2]: switching child
            // replaces the shown child, so Back cannot reach the
            // previous one's data. Results and payments are pushes
            // the guardian asks for explicitly.
            actions =
                GuardianActions(
                    onSelect = model::select,
                    // **Pay opens the child's payments first** (G1 → G3):
                    // what was already paid sits above Send money, so a
                    // guardian does not pay twice for want of seeing it.
                    onPay = { option -> navController.navigate(Destination.ChildPayments.of(option.enrollmentId)) },
                    onPayments = { seat -> navController.navigate(Destination.ChildPayments.of(seat)) },
                    onResult = { result, _ ->
                        navController.navigate(
                            Destination.Dashboard.of(result.enrollmentId, DashboardReader.GUARDIAN.name),
                        )
                    },
                    onBatch = { seat -> navController.navigate(Destination.ChildBatch.of(seat)) },
                    onRetry = model::retry,
                    onRefresh = model::refresh,
                    onReviews =
                        { navController.navigate(Destination.HubMyReviews.route) }
                            .takeIf { reviewsState.showsEntry },
                ),
            refreshing = refreshing,
            // **No bottom bar for a guardian** (G1, G4): More opens
            // from the profile button beside the bell.
            barActions = { FamilyBarActions(client, navController) },
        )
    }
}

/**
 * The guardian's per-child destinations: payments (G3) and paying.
 *
 * Paying is S3's flow on the guardian's own routes, so the student and
 * the guardian see one form and one set of rules.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.guardianRoutes(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(
        route = Destination.ChildPayments.route,
        arguments = listOf(navArgument(Destination.ChildPayments.ARG_SEAT) { type = NavType.StringType }),
    ) { entry ->
        val seat = entry.arguments?.getString(Destination.ChildPayments.ARG_SEAT).orEmpty()
        val model: PaymentsViewModel =
            viewModel(key = "payments-$seat") { PaymentsViewModel(HttpGuardianRepository(client)) }
        val state by model.state.collectAsState()

        LaunchedEffect(seat) { model.load(seat) }

        PaymentsScreen(
            state = state,
            onBack = { navController.popBackStack() },
            onPay = { navController.navigate(Destination.ChildPay.of(seat)) },
            onRetry = { model.load(seat) },
        )
    }

    composable(
        route = Destination.ChildPay.route,
        arguments = listOf(navArgument(Destination.ChildPay.ARG_SEAT) { type = NavType.StringType }),
    ) { entry ->
        val seat = entry.arguments?.getString(Destination.ChildPay.ARG_SEAT).orEmpty()
        val model: PayViewModel =
            viewModel(key = "child-pay-$seat") { PayViewModel(HttpPayRepository(client, FamilyReader.GUARDIAN)) }
        val state by model.state.collectAsState()

        LaunchedEffect(seat) { model.load(seat) }

        PayScreen(
            state = state,
            actions =
                PayActions(
                    onClose = { navController.popBackStack() },
                    onChoose = model::choose,
                    onBack = model::back,
                    onBatch = model::chooseBatch,
                    onToggleChild = model::toggleChild,
                    onChooseFee = model::chooseFee,
                    onType = model::type,
                    onSend = model::send,
                    onRetry = { model.load(seat) },
                ),
        )
    }
}
