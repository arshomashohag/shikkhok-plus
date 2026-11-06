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
import com.shikkhokplus.app.core.network.HttpExtraFeesRepository
import com.shikkhokplus.app.core.network.HttpFeesRepository
import com.shikkhokplus.app.feature.extrafees.ExtraFeeDetailViewModel
import com.shikkhokplus.app.feature.extrafees.ExtraFeesViewModel
import com.shikkhokplus.app.feature.extrafees.RaiseFeeViewModel
import com.shikkhokplus.app.feature.extrafees.ui.ExtraFeeDetailScreen
import com.shikkhokplus.app.feature.extrafees.ui.ExtraFeesScreen
import com.shikkhokplus.app.feature.extrafees.ui.RaiseFeeActions
import com.shikkhokplus.app.feature.extrafees.ui.RaiseFeeScreen
import com.shikkhokplus.app.feature.fees.ui.RecordActions
import com.shikkhokplus.app.feature.fees.ui.RecordPaymentSheetView
import io.ktor.client.HttpClient

/**
 * A batch's exam and other fees: the list, raising one, and one fee's
 * students with recording cash against it.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.extraFeesRoutes(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(
        route = Destination.ExtraFees.route,
        arguments = listOf(navArgument(Destination.ExtraFees.ARG_BATCH) { type = NavType.StringType }),
    ) { entry ->
        val batchId = entry.arguments?.getString(Destination.ExtraFees.ARG_BATCH).orEmpty()
        val model: ExtraFeesViewModel =
            viewModel(key = "extra-fees-$batchId") { ExtraFeesViewModel(HttpExtraFeesRepository(client)) }
        val state by model.state.collectAsState()
        // Re-read on every return, so a just-raised fee is listed.
        LaunchedEffect(batchId) { model.load(batchId) }
        ExtraFeesScreen(
            state = state,
            onOpen = { navController.navigate(Destination.ExtraFeeDetail.of(it)) },
            onRaise = { navController.navigate(Destination.RaiseExtraFee.of(batchId)) },
            onRetry = model::retry,
            onBack = { navController.popBackStack() },
        )
    }

    composable(
        route = Destination.RaiseExtraFee.route,
        arguments = listOf(navArgument(Destination.RaiseExtraFee.ARG_BATCH) { type = NavType.StringType }),
    ) { entry ->
        val batchId = entry.arguments?.getString(Destination.RaiseExtraFee.ARG_BATCH).orEmpty()
        val model: RaiseFeeViewModel = viewModel { RaiseFeeViewModel(HttpExtraFeesRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(batchId) { model.load(batchId) }
        LaunchedEffect(state.raised) {
            state.raised?.let { fee ->
                navController.navigate(Destination.ExtraFeeDetail.of(fee.extraFeeId)) {
                    popUpTo(Destination.RaiseExtraFee.route) { inclusive = true }
                }
            }
        }
        RaiseFeeScreen(
            state = state,
            actions =
                RaiseFeeActions(
                    onKind = model::kind,
                    onLabel = model::label,
                    onExam = model::exam,
                    onAmount = model::amount,
                    onDueOn = model::dueOn,
                    onChoose = model::choose,
                    onRaise = model::raise,
                    onRetry = model::retry,
                    onCancel = { navController.popBackStack() },
                ),
        )
    }

    composable(
        route = Destination.ExtraFeeDetail.route,
        arguments = listOf(navArgument(Destination.ExtraFeeDetail.ARG_FEE) { type = NavType.StringType }),
    ) { entry ->
        val feeId = entry.arguments?.getString(Destination.ExtraFeeDetail.ARG_FEE).orEmpty()
        val model: ExtraFeeDetailViewModel =
            viewModel(key = "extra-fee-$feeId") {
                ExtraFeeDetailViewModel(HttpExtraFeesRepository(client), HttpFeesRepository(client))
            }
        val state by model.state.collectAsState()
        val sheet by model.sheet.collectAsState()
        val recorded by model.recorded.collectAsState()
        LaunchedEffect(feeId) { model.load(feeId) }
        ExtraFeeDetailScreen(
            state = state,
            recorded = recorded,
            onRecord = model::openRecord,
            onRetry = model::retry,
            onBack = { navController.popBackStack() },
        )
        sheet?.let {
            RecordPaymentSheetView(
                sheet = it,
                actions =
                    RecordActions(
                        onType = model::typeRecordAmount,
                        onChannel = model::chooseRecordChannel,
                        onReference = model::typeRecordReference,
                        onNote = model::typeRecordNote,
                        onDisposition = model::chooseRecordDisposition,
                        onConfirm = model::confirmRecord,
                        onDismiss = model::dismissRecord,
                    ),
            )
        }
    }
}
