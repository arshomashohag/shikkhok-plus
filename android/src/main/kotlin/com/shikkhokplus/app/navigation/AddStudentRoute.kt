package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.ScreenScaffold
import com.shikkhokplus.app.core.network.HttpBatchDetailRepository
import com.shikkhokplus.app.core.network.HttpRosterRepository
import com.shikkhokplus.app.feature.batchdetail.BatchDetailViewModel
import com.shikkhokplus.app.core.ui.StudentAddForm
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.roster.RosterViewModel
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.feature.roster.RosterUiState
import io.ktor.client.HttpClient

/**
 * T8, adding students to a batch, with "Save" and "Save & add next".
 *
 * **Save closes; Save & add next stays** (T8). A teacher entering a new
 * batch's roster adds a dozen students in a row, and returning to the
 * roster after each one is the slow part. After a confirmed add-next the
 * form clears and the bar counts how many were added; either way the
 * form waits for the server's answer before it moves, so a refused add
 * is shown beside what was typed rather than lost.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 */
internal fun NavGraphBuilder.addStudentRoute(
    client: HttpClient,
    navController: NavHostController,
) {
    composable(
        route = Destination.AddStudent.route,
        arguments = listOf(navArgument(Destination.Roster.ARG_ID) { type = NavType.StringType }),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.Roster.ARG_ID).orEmpty()

        // The roster's ViewModel, so each added student is in the list
        // this form returns to.
        val parent = remember(entry) { navController.getBackStackEntry(Destination.Roster.route) }
        val model: RosterViewModel = viewModel(parent, key = id) { RosterViewModel(HttpRosterRepository(client)) }
        val write by model.writeState.collectAsState()
        // The batch's own fee, from the screen this form was opened on,
        // so the form can offer it as "Batch fee · ৳1,200" (T8).
        val detail: BatchDetailViewModel =
            viewModel(parent, key = "detail-$id") { BatchDetailViewModel(HttpBatchDetailRepository(client)) }
        val batchFee = detail.state.collectAsState().value.header?.defaultFee?.let(Numerals::money)
        val roster by model.state.collectAsState()
        val batchName =
            (roster as? RosterUiState.Loaded)?.batchName ?: (roster as? RosterUiState.Empty)?.batchName
        val existing = (roster as? RosterUiState.Loaded)?.rows?.map { it.displayName }.orEmpty()
        var addNext by remember { mutableStateOf(false) }
        var added by rememberSaveable { mutableIntStateOf(0) }

        LaunchedEffect(write) {
            if (write == WriteState.Saved) {
                model.acknowledgeWrite()
                if (addNext) added += 1 else navController.popBackStack()
            }
        }
        val leave = {
            model.acknowledgeWrite()
            navController.popBackStack()
            Unit
        }

        AddStudentPage(added = added, batchName = batchName, onBack = leave) {
            // Keyed on the count, so a confirmed add-next starts a fresh,
            // empty form rather than one holding the last student.
            key(added) {
                StudentAddForm(
                    onAdd = { name, phone, guardian, fee ->
                        addNext = false
                        model.addStudent(name, phone, guardian, fee)
                    },
                    onAddNext = { name, phone, guardian, fee ->
                        addNext = true
                        model.addStudent(name, phone, guardian, fee)
                    },
                    onCancel = leave,
                    existingNames = existing,
                    batchFee = batchFee,
                    saving = write == WriteState.Saving,
                    error = writeError(write),
                )
            }
        }
    }
}

/**
 * The page around the form: the title, and "2 added so far" once a
 * save-and-add-next has landed.
 *
 * @param added How many students this visit added
 * @param batchName The batch being added to, or null before it loads
 * @param onBack Called to leave
 * @param form The form
 */
@Composable
private fun AddStudentPage(added: Int, batchName: String?, onBack: () -> Unit, form: @Composable () -> Unit) {
    val count = if (added > 0) pluralStringResource(R.plurals.student_add_added_so_far, added, added) else null
    ScreenScaffold(
        title = stringResource(R.string.screen_title_add_student),
        // "Physics A · 2 added so far" (T8).
        subtitle = listOfNotNull(batchName?.let(Numerals::freeText), count).joinToString(" · ").ifEmpty { null },
        onBack = onBack,
    ) {
        form()
    }
}
