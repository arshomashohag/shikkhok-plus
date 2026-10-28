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
import com.shikkhokplus.app.core.network.HttpChildPayRepository
import com.shikkhokplus.app.core.network.HttpGuardianRepository
import com.shikkhokplus.app.feature.guardian.ChildProgressViewModel
import com.shikkhokplus.app.feature.guardian.PaymentsViewModel
import com.shikkhokplus.app.feature.guardian.ui.ChildProgressScreen
import com.shikkhokplus.app.feature.guardian.ui.PaymentsScreen
import com.shikkhokplus.app.feature.pay.PayViewModel
import com.shikkhokplus.app.feature.pay.ui.PayActions
import com.shikkhokplus.app.feature.pay.ui.PayScreen
import io.ktor.client.HttpClient

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
            onPay = { option -> navController.navigate(Destination.ChildPay.of(option.enrollmentId)) },
            onRetry = { model.load(seat) },
        )
    }

    composable(
        route = Destination.ChildProgress.route,
        arguments = listOf(navArgument(Destination.ChildProgress.ARG_SEAT) { type = NavType.StringType }),
    ) { entry ->
        val seat = entry.arguments?.getString(Destination.ChildProgress.ARG_SEAT).orEmpty()
        val model: ChildProgressViewModel =
            viewModel(key = "progress-$seat") { ChildProgressViewModel(HttpGuardianRepository(client)) }
        val state by model.state.collectAsState()

        LaunchedEffect(seat) { model.load(seat) }

        ChildProgressScreen(
            state = state,
            onBack = { navController.popBackStack() },
            onSelect = model::select,
            onRetry = model::retry,
        )
    }

    composable(
        route = Destination.ChildPay.route,
        arguments = listOf(navArgument(Destination.ChildPay.ARG_SEAT) { type = NavType.StringType }),
    ) { entry ->
        val seat = entry.arguments?.getString(Destination.ChildPay.ARG_SEAT).orEmpty()
        val model: PayViewModel =
            viewModel(key = "child-pay-$seat") { PayViewModel(HttpChildPayRepository(client, seat)) }
        val state by model.state.collectAsState()

        LaunchedEffect(seat) { model.load(seat) }

        PayScreen(
            state = state,
            actions =
                PayActions(
                    onClose = { navController.popBackStack() },
                    onChoose = model::choose,
                    onChange = model::change,
                    onType = model::type,
                    onSend = model::send,
                    onRetry = { model.load(seat) },
                ),
        )
    }
}
