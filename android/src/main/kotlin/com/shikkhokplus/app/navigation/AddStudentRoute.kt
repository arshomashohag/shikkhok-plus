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
import com.shikkhokplus.app.core.network.HttpRosterRepository
import com.shikkhokplus.app.core.ui.StudentAddForm
import com.shikkhokplus.app.core.ui.WriteState
import com.shikkhokplus.app.feature.roster.RosterViewModel
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

        AddStudentPage(added = added, onBack = leave) {
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
 * @param onBack Called to leave
 * @param form The form
 */
@Composable
private fun AddStudentPage(added: Int, onBack: () -> Unit, form: @Composable () -> Unit) {
    ScreenScaffold(
        title = stringResource(R.string.screen_title_add_student),
        subtitle = if (added > 0) pluralStringResource(R.plurals.student_add_added_so_far, added, added) else null,
        onBack = onBack,
    ) {
        form()
    }
}
