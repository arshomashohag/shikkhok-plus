package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.core.network.HttpPayrollRepository
import com.shikkhokplus.app.feature.payroll.MyPayViewModel
import com.shikkhokplus.app.feature.payroll.PayrollViewModel
import com.shikkhokplus.app.feature.payroll.ui.MyPayScreen
import com.shikkhokplus.app.feature.payroll.ui.PayrollActions
import com.shikkhokplus.app.feature.payroll.ui.PayrollScreen
import io.ktor.client.HttpClient

/**
 * The chosen centre's payroll, and a centre teacher's own pay.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 * @param bottomBar The centre teacher's tab bar, shown on My pay
 */
internal fun NavGraphBuilder.payrollRoutes(
    client: HttpClient,
    navController: NavHostController,
    bottomBar: @Composable () -> Unit,
) {
    composable(Destination.CentrePayroll.route) {
        val model: PayrollViewModel = viewModel { PayrollViewModel(HttpPayrollRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        PayrollScreen(
            state = state,
            actions =
                PayrollActions(
                    onShift = model::shift,
                    onDraw = model::draw,
                    onApprove = model::approve,
                    onOpenAdjust = model::openAdjust,
                    onOpenPay = model::openPay,
                    onRemoveAdjustment = model::removeAdjustment,
                    onKind = { model.adjustment(kind = it) },
                    onLabel = { model.adjustment(label = it) },
                    onAdjustAmount = { model.adjustment(amount = it) },
                    onPayAmount = { model.payment(amount = it) },
                    onPaidOn = { model.payment(paidOn = it) },
                    onNote = { model.payment(note = it) },
                    onSubmit = model::submit,
                    onClose = model::close,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.MyPay.route) {
        val model: MyPayViewModel = viewModel { MyPayViewModel(HttpPayrollRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        MyPayScreen(state = state, onRetry = model::retry, bottomBar = bottomBar)
    }
}
