package com.shikkhokplus.app.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.core.network.HttpExaminerRepository
import com.shikkhokplus.app.core.network.HttpMyExamsRepository
import com.shikkhokplus.app.feature.myexams.ExaminerViewModel
import com.shikkhokplus.app.feature.myexams.MyExamMarksViewModel
import com.shikkhokplus.app.feature.myexams.MyExamsViewModel
import com.shikkhokplus.app.feature.myexams.ui.ExaminerControl
import com.shikkhokplus.app.feature.myexams.ui.MyExamMarksActions
import com.shikkhokplus.app.feature.myexams.ui.MyExamMarksScreen
import com.shikkhokplus.app.feature.myexams.ui.MyExamsScreen
import io.ktor.client.HttpClient

/**
 * An examiner's screens: the exams a centre asked them to mark, and one
 * exam's marks.
 *
 * @param client The authenticated HTTP client
 * @param navController The controller to navigate with
 * @param bottomBar The centre teacher's tab bar, shown on My exams
 */
internal fun NavGraphBuilder.myExamsRoutes(
    client: HttpClient,
    navController: NavHostController,
    bottomBar: @Composable () -> Unit,
) {
    composable(Destination.MyExams.route) {
        val model: MyExamsViewModel = viewModel { MyExamsViewModel(HttpMyExamsRepository(client)) }
        val state by model.state.collectAsState()
        // Re-read on every return, so a publish shows on the list.
        LaunchedEffect(Unit) { model.load() }
        MyExamsScreen(
            state = state,
            onOpen = { navController.navigate(Destination.MyExamMarks.of(it)) },
            onRetry = model::retry,
            bottomBar = bottomBar,
        )
    }

    composable(
        route = Destination.MyExamMarks.route,
        arguments = listOf(navArgument(Destination.MyExamMarks.ARG_EXAM) { type = NavType.StringType }),
    ) { entry ->
        val examId = entry.arguments?.getString(Destination.MyExamMarks.ARG_EXAM).orEmpty()
        val model: MyExamMarksViewModel = viewModel { MyExamMarksViewModel(HttpMyExamsRepository(client), examId) }
        val state by model.state.collectAsState()
        LaunchedEffect(examId) { model.load() }
        MyExamMarksScreen(
            state = state,
            actions =
                MyExamMarksActions(
                    onType = model::type,
                    onSave = model::save,
                    onAbsent = model::absent,
                    onPublish = model::publish,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}

/**
 * The examiner control for one exam, for a manager in a centre.
 *
 * @param client The authenticated HTTP client
 * @param examId The exam
 */
@Composable
internal fun ExaminerSlot(client: HttpClient, examId: String) {
    val model: ExaminerViewModel =
        viewModel(key = "examiner-$examId") { ExaminerViewModel(HttpExaminerRepository(client), examId) }
    val state by model.state.collectAsState()
    LaunchedEffect(examId) { model.load() }
    ExaminerControl(state = state, onChoose = model::choose)
}
