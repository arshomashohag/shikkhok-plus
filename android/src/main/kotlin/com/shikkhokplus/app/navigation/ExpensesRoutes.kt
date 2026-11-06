package com.shikkhokplus.app.navigation

import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.core.network.HttpExpensesRepository
import com.shikkhokplus.app.feature.expenses.ExpensesViewModel
import com.shikkhokplus.app.feature.expenses.RecordExpenseViewModel
import com.shikkhokplus.app.feature.expenses.SummaryViewModel
import com.shikkhokplus.app.feature.expenses.ui.ExpensesActions
import com.shikkhokplus.app.feature.expenses.ui.ExpensesScreen
import com.shikkhokplus.app.feature.expenses.ui.RecordExpenseActions
import com.shikkhokplus.app.feature.expenses.ui.RecordExpenseScreen
import com.shikkhokplus.app.feature.expenses.ui.SummaryActions
import com.shikkhokplus.app.feature.expenses.ui.SummaryScreen
import io.ktor.client.HttpClient

/**
 * The owner's spending: the expense list, recording an expense, and the
 * monthly summary. Each screen opens the other from its top bar, so the
 * two replace each other rather than stacking.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 */
internal fun NavGraphBuilder.expensesRoutes(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(Destination.Expenses.route) {
        val model: ExpensesViewModel = viewModel { ExpensesViewModel(HttpExpensesRepository(client)) }
        val state by model.state.collectAsState()
        // Re-read on every return, so a just-recorded expense is listed.
        LaunchedEffect(Unit) { model.load() }
        ExpensesScreen(
            state = state,
            actions =
                ExpensesActions(
                    onShift = model::shift,
                    onRecord = { navController.navigate(Destination.RecordExpense.route) },
                    onVoid = model::void,
                    onRetry = model::retry,
                    onOpenSummary = {
                        navController.navigate(Destination.MoneySummary.route) {
                            popUpTo(Destination.Expenses.route) { inclusive = true }
                        }
                    },
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.RecordExpense.route) {
        val model: RecordExpenseViewModel = viewModel { RecordExpenseViewModel(HttpExpensesRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(state.saved) { if (state.saved) navController.popBackStack() }
        RecordExpenseScreen(
            state = state,
            actions =
                RecordExpenseActions(
                    onCategory = model::category,
                    onWhat = model::what,
                    onAmount = model::amount,
                    onSpentOn = model::spentOn,
                    onPayee = model::payee,
                    onNote = model::note,
                    onSave = model::save,
                    onCancel = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.MoneySummary.route) {
        val model: SummaryViewModel = viewModel { SummaryViewModel(HttpExpensesRepository(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        SummaryScreen(
            state = state,
            actions =
                SummaryActions(
                    onShift = model::shift,
                    onRetry = model::retry,
                    onOpenExpenses = {
                        navController.navigate(Destination.Expenses.route) {
                            popUpTo(Destination.MoneySummary.route) { inclusive = true }
                        }
                    },
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}
