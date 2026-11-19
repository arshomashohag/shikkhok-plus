package com.shikkhokplus.app.navigation

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.feature.hubenquiry.EnquiryFormViewModel
import com.shikkhokplus.app.feature.hubenquiry.EnquiryLink
import com.shikkhokplus.app.feature.hubenquiry.HttpHubEnquiryApi
import com.shikkhokplus.app.feature.hubenquiry.MyEnquiriesViewModel
import com.shikkhokplus.app.feature.hubenquiry.OwnerEnquiriesViewModel
import com.shikkhokplus.app.feature.hubenquiry.OwnerEnquiryViewModel
import com.shikkhokplus.app.feature.hubenquiry.showsEntry
import com.shikkhokplus.app.feature.hubenquiry.ui.EnquiryFormActions
import com.shikkhokplus.app.feature.hubenquiry.ui.EnquiryFormScreen
import com.shikkhokplus.app.feature.hubenquiry.ui.MyEnquiriesActions
import com.shikkhokplus.app.feature.hubenquiry.ui.MyEnquiriesScreen
import com.shikkhokplus.app.feature.hubenquiry.ui.OwnerEnquiriesActions
import com.shikkhokplus.app.feature.hubenquiry.ui.OwnerEnquiriesScreen
import com.shikkhokplus.app.feature.hubenquiry.ui.OwnerEnquiryActions
import com.shikkhokplus.app.feature.hubenquiry.ui.OwnerEnquiryDetailScreen
import io.ktor.client.HttpClient

/**
 * Join requests [H5]: the guardian's form, opened from a public page's
 * "Ask to join" App Link; the caller's own requests, opened from More or
 * an answered-request inbox item; and the owner's inbox and one request,
 * opened from the listing editor's "Join requests" row or a new-request
 * inbox item. "Add as student" opens the add-student form with the
 * request's id (`teacherStudentsRoutes`), which answers once it saves.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 */
internal fun NavGraphBuilder.hubEnquiryRoutes(client: HttpClient, navController: NavHostController) {
    composable(
        route = Destination.HubEnquiryForm.route,
        arguments =
            listOf(
                navArgument(Destination.HubEnquiryForm.ARG_OWNER) {
                    type = NavType.StringType
                    defaultValue = ""
                },
                navArgument(Destination.HubEnquiryForm.ARG_BATCH) {
                    type = NavType.StringType
                    nullable = true
                    defaultValue = null
                },
            ),
    ) { entry ->
        val owner = entry.arguments?.getString(Destination.HubEnquiryForm.ARG_OWNER)
        val batch = entry.arguments?.getString(Destination.HubEnquiryForm.ARG_BATCH)
        val model: EnquiryFormViewModel =
            viewModel(key = "hub-enquiry/$owner/$batch") {
                EnquiryFormViewModel(HttpHubEnquiryApi(client), EnquiryLink(owner, batch))
            }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        EnquiryFormScreen(
            state = state,
            actions =
                EnquiryFormActions(
                    onName = model::editName,
                    onLevel = model::pickLevel,
                    onMessage = model::editMessage,
                    onShare = model::chooseShare,
                    onDeclare = model::declare,
                    onSend = model::send,
                    onRetry = model::retry,
                    onRetryLoad = model::retryLoad,
                    onMine = { navController.navigate(Destination.HubMyEnquiries.route) },
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.HubMyEnquiries.route) {
        val model: MyEnquiriesViewModel = viewModel { MyEnquiriesViewModel(HttpHubEnquiryApi(client)) }
        val state by model.state.collectAsState()
        val context = LocalContext.current
        LaunchedEffect(Unit) { model.load() }
        MyEnquiriesScreen(
            state = state,
            actions =
                MyEnquiriesActions(
                    onWithdraw = model::askWithdraw,
                    onConfirmWithdraw = model::confirmWithdraw,
                    onCancelWithdraw = model::cancelWithdraw,
                    onRetryWithdraw = model::retryWithdraw,
                    onCall = { phone -> openOutside(context, Intent.ACTION_DIAL, "tel:$phone") },
                    onRetry = model::load,
                    onDismissNotice = model::dismissNotice,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.HubOwnerEnquiries.route) {
        val model: OwnerEnquiriesViewModel = viewModel { OwnerEnquiriesViewModel(HttpHubEnquiryApi(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        OwnerEnquiriesScreen(
            state = state,
            actions =
                OwnerEnquiriesActions(
                    onOpen = { row -> navController.navigate(Destination.HubOwnerEnquiry.of(row.id)) },
                    onRetry = model::load,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    ownerEnquiryRoute(client, navController)
}

/**
 * One request for its owner, with the answers the server offers.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 */
private fun NavGraphBuilder.ownerEnquiryRoute(client: HttpClient, navController: NavHostController) {
    composable(
        route = Destination.HubOwnerEnquiry.route,
        arguments = listOf(navArgument(Destination.HubOwnerEnquiry.ARG_ID) { type = NavType.StringType }),
    ) { entry ->
        val id = entry.arguments?.getString(Destination.HubOwnerEnquiry.ARG_ID).orEmpty()
        val model: OwnerEnquiryViewModel =
            viewModel(key = "hub-owner-enquiry/$id") { OwnerEnquiryViewModel(HttpHubEnquiryApi(client), id) }
        val state by model.state.collectAsState()
        val context = LocalContext.current
        // On every return, so the answer the add-student form gave shows here.
        LaunchedEffect(Unit) { model.load() }
        OwnerEnquiryDetailScreen(
            state = state,
            actions =
                OwnerEnquiryActions(
                    // Adding is the add-student form's to finish: it saves, then answers.
                    onAdd = { enquiry ->
                        navController.navigate(Destination.NewStudent.of(enquiry.batchId, enquiry.id))
                    },
                    onAnswer = model::answer,
                    onRetry = model::retry,
                    onRetryLoad = model::retryLoad,
                    onCall = { phone -> openOutside(context, Intent.ACTION_DIAL, "tel:$phone") },
                    onEmail = { email -> openOutside(context, Intent.ACTION_SENDTO, "mailto:$email") },
                    onDismissNotice = model::dismissNotice,
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}

/**
 * More's "My join requests", for any lens: an opener only once the server
 * lists at least one request, read again on each visit to More.
 *
 * @param client The authenticated HTTP client
 * @param open Opens the list
 * @return The opener, or null while the server lists none
 */
@Composable
internal fun myEnquiriesOpener(client: HttpClient, open: () -> Unit): (() -> Unit)? {
    val model: MyEnquiriesViewModel =
        viewModel(key = "hub-my-enquiries-entry") { MyEnquiriesViewModel(HttpHubEnquiryApi(client)) }
    val state by model.state.collectAsState()
    LaunchedEffect(Unit) { model.load() }
    return open.takeIf { state.showsEntry }
}

/**
 * The listing editor's "Join requests": an opener only once
 * `GET /v1/hub/enquiries` answered. Switched off, or on any failure, there
 * is no row and no error.
 *
 * @param client The authenticated HTTP client
 * @param open Opens the inbox
 * @return The opener, or null
 */
@Composable
internal fun ownerEnquiriesOpener(client: HttpClient, open: () -> Unit): (() -> Unit)? {
    val model: OwnerEnquiriesViewModel =
        viewModel(key = "hub-owner-enquiries-entry") { OwnerEnquiriesViewModel(HttpHubEnquiryApi(client)) }
    val state by model.state.collectAsState()
    LaunchedEffect(Unit) { model.load() }
    return open.takeIf { state.showsEntry }
}

/**
 * Hand a phone number or an email address to the phone's dialler or mail
 * app, outside this one. A phone with neither shows nothing rather than
 * crashing; the number or address is still on screen to copy.
 *
 * @param context The activity context
 * @param action `ACTION_DIAL` or `ACTION_SENDTO`
 * @param uri The `tel:` or `mailto:` address
 */
private fun openOutside(context: Context, action: String, uri: String) {
    try {
        context.startActivity(Intent(action, Uri.parse(uri)))
    } catch (_: ActivityNotFoundException) {
        // Nothing on this phone handles it.
    }
}
