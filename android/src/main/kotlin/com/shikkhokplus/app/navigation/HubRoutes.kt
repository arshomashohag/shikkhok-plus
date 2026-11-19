package com.shikkhokplus.app.navigation

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.shikkhokplus.app.BuildConfig
import com.shikkhokplus.app.feature.hublisting.BatchListingsViewModel
import com.shikkhokplus.app.feature.hublisting.HttpHubApi
import com.shikkhokplus.app.feature.hublisting.HttpHubFeedbackApi
import com.shikkhokplus.app.feature.hublisting.HubFeedbackViewModel
import com.shikkhokplus.app.feature.hublisting.HubListingViewModel
import com.shikkhokplus.app.feature.hublisting.HubPreviewViewModel
import com.shikkhokplus.app.feature.hublisting.NameConsentViewModel
import com.shikkhokplus.app.feature.hublisting.hubLocale
import com.shikkhokplus.app.feature.hublisting.publicPageUrl
import com.shikkhokplus.app.feature.hublisting.ui.BatchListingsActions
import com.shikkhokplus.app.feature.hublisting.ui.BatchListingsScreen
import com.shikkhokplus.app.feature.hublisting.ui.HubFeedbackActions
import com.shikkhokplus.app.feature.hublisting.ui.HubFeedbackScreen
import com.shikkhokplus.app.feature.hublisting.ui.HubListingActions
import com.shikkhokplus.app.feature.hublisting.ui.HubListingScreen
import com.shikkhokplus.app.feature.hublisting.ui.HubPreviewActions
import com.shikkhokplus.app.feature.hublisting.ui.HubPreviewScreen
import com.shikkhokplus.app.feature.hublisting.report.HttpHubReportApi
import com.shikkhokplus.app.feature.hublisting.report.HubReportViewModel
import com.shikkhokplus.app.feature.hublisting.report.ReportLink
import com.shikkhokplus.app.feature.hublisting.report.ui.HubReportActions
import com.shikkhokplus.app.feature.hublisting.report.ui.HubReportScreen
import com.shikkhokplus.app.feature.hublisting.ui.NameConsentScreen
import com.shikkhokplus.app.feature.hubenquiry.EnquiryLink
import com.shikkhokplus.app.feature.hubreviews.HttpHubReviewsApi
import com.shikkhokplus.app.feature.hubreviews.MyReviewsViewModel
import com.shikkhokplus.app.feature.hubreviews.OwnerReviewsViewModel
import com.shikkhokplus.app.feature.hubreviews.ReviewEditorViewModel
import com.shikkhokplus.app.feature.hubreviews.showsEntry
import com.shikkhokplus.app.feature.hubreviews.ui.MyReviewsActions
import com.shikkhokplus.app.feature.hubreviews.ui.MyReviewsScreen
import com.shikkhokplus.app.feature.hubreviews.ui.OwnerReviewsActions
import com.shikkhokplus.app.feature.hubreviews.ui.OwnerReviewsScreen
import com.shikkhokplus.app.feature.hubreviews.ui.ReviewEditorActions
import com.shikkhokplus.app.feature.hubreviews.ui.ReviewEditorScreen
import com.shikkhokplus.app.feature.hublisting.report.ReportKind
import com.shikkhokplus.app.feature.hubmedia.BucketClient
import com.shikkhokplus.app.feature.hubmedia.HttpHubMediaApi
import com.shikkhokplus.app.feature.hubmedia.HubMediaViewModel
import com.shikkhokplus.app.feature.hubmedia.pickedPhoto
import com.shikkhokplus.app.feature.hubmedia.ui.HubPhotosActions
import com.shikkhokplus.app.feature.hubmedia.ui.HubPhotosScreen
import io.ktor.client.HttpClient

/**
 * The public hub's owner screens, pushed over More: the listing editor,
 * its preview, its batch listings, the photos of either, and a centre
 * member's name consent; guardian reviews and the owner's Reviews screen;
 * and the demand question, opened from its inbox item; join requests
 * ([hubEnquiryRoutes]); and, for any signed-in reader, reporting a public
 * hub page, opened from that page's App Link.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 * @param siteUrl The public site's origin, or null when the build names
 *   none; then "View public page" is not offered
 * @param bucket The bare client photos are posted to the bucket with,
 *   which never carries the session; see [BucketClient]
 */
internal fun NavGraphBuilder.hubRoutes(
    client: HttpClient,
    navController: NavHostController,
    siteUrl: String? = BuildConfig.SITE_URL.ifBlank { null },
    bucket: HttpClient = BucketClient.shared,
) {
    composable(Destination.HubListing.route) {
        val model: HubListingViewModel = viewModel { HubListingViewModel(HttpHubApi(client)) }
        val state by model.state.collectAsState()
        // The Reviews row is drawn only once `GET /v1/hub/reviews` answered:
        // switched off, or on any failure, it is simply not there [T11-d].
        val reviews: OwnerReviewsViewModel =
            viewModel(key = "hub-reviews-entry") { OwnerReviewsViewModel(HttpHubReviewsApi(client)) }
        val reviewsState by reviews.state.collectAsState()
        // The Join requests row likewise, only once `GET /v1/hub/enquiries` answered [H5].
        val enquiries = ownerEnquiriesOpener(client) { navController.navigate(Destination.HubOwnerEnquiries.route) }
        val context = LocalContext.current
        // The language the app is drawn in, which the public pages share.
        val locale = hubLocale(LocalConfiguration.current.locales[0].language)
        LaunchedEffect(Unit) {
            model.load()
            reviews.load()
        }
        HubListingScreen(
            state = state,
            actions =
                HubListingActions(
                    onEdit = model::edit,
                    onToggleMode = model::toggleMode,
                    onPickDivision = model::pickDivision,
                    onPickDistrict = model::pickDistrict,
                    onPickUpazila = model::pickUpazila,
                    onPickThana = model::pickThana,
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
                    onPhotos = { readOnly -> navController.navigate(Destination.HubPhotos.of(null, readOnly)) },
                    onPreview = { navController.navigate(Destination.HubPreview.of(locale)) },
                    onReviews =
                        { navController.navigate(Destination.HubOwnerReviews.route) }
                            .takeIf { reviewsState.showsEntry },
                    onEnquiries = enquiries,
                    onAcceptsEnquiries = model::setAcceptsEnquiries,
                    onRetrySwitch = model::retrySwitch,
                    onViewPublic =
                        siteUrl?.let { site ->
                            { slug -> openInBrowser(context, publicPageUrl(site, locale, slug)) }
                        },
                    // A suspended owner appeals by asking Help.
                    onAppeal = { navController.navigate(Destination.AskQuestion.route) },
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(
        route = Destination.HubPreview.route,
        arguments =
            listOf(
                navArgument(Destination.HubPreview.ARG_LOCALE) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
    ) { entry ->
        val asked = entry.arguments?.getString(Destination.HubPreview.ARG_LOCALE)
        val model: HubPreviewViewModel = viewModel { HubPreviewViewModel(HttpHubApi(client), hubLocale(asked)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        HubPreviewScreen(
            state = state,
            actions =
                HubPreviewActions(
                    onLocale = model::switchLocale,
                    onRetry = model::retry,
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
                    onPhotos = { batchId, readOnly ->
                        navController.navigate(Destination.HubPhotos.of(batchId, readOnly))
                    },
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    hubPhotosRoute(client, bucket, navController)
    hubReviewsRoutes(client, navController)
    hubEnquiryRoutes(client, navController)

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

    composable(
        route = Destination.HubFeedback.route,
        arguments =
            listOf(
                navArgument(Destination.HubFeedback.ARG_OWNER) { type = NavType.StringType },
                navArgument(Destination.HubFeedback.ARG_DAY) { type = NavType.IntType },
            ),
    ) { entry ->
        val ownerId = entry.arguments?.getString(Destination.HubFeedback.ARG_OWNER).orEmpty()
        val day = entry.arguments?.getInt(Destination.HubFeedback.ARG_DAY) ?: 0
        val model: HubFeedbackViewModel =
            viewModel(key = "$ownerId/$day") { HubFeedbackViewModel(HttpHubFeedbackApi(client), ownerId, day) }
        val state by model.state.collectAsState()
        HubFeedbackScreen(
            state = state,
            actions =
                HubFeedbackActions(
                    onAnswer = model::answer,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(
        route = Destination.HubReport.route,
        arguments =
            listOf(
                navArgument(Destination.HubReport.ARG_KIND) {
                    type = NavType.StringType
                    defaultValue = ""
                },
                navArgument(Destination.HubReport.ARG_ID) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
    ) { entry ->
        val kind = entry.arguments?.getString(Destination.HubReport.ARG_KIND)
        val id = entry.arguments?.getString(Destination.HubReport.ARG_ID)
        val model: HubReportViewModel =
            viewModel(key = "hub-report/$kind/$id") {
                HubReportViewModel(HttpHubReportApi(client), ReportLink(kind, id))
            }
        val state by model.state.collectAsState()
        HubReportScreen(
            state = state,
            actions =
                HubReportActions(
                    onReason = model::pickReason,
                    onNote = model::editNote,
                    onSend = model::send,
                    onRetry = model::retry,
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}

/**
 * One gallery's photos: the owner's own (no batch) or one batch's.
 *
 * "Add a photo" opens the system photo picker for images only, which
 * needs no permission; the content resolver gives the file's type and
 * size, and the bytes go to the bucket on [bucket], never on [client].
 *
 * @param client The authenticated HTTP client
 * @param bucket The bare bucket client
 * @param navController The app's controller
 */
private fun NavGraphBuilder.hubPhotosRoute(
    client: HttpClient,
    bucket: HttpClient,
    navController: NavHostController,
) {
    composable(
        route = Destination.HubPhotos.route,
        arguments =
            listOf(
                navArgument(Destination.HubPhotos.ARG_BATCH) {
                    type = NavType.StringType
                    defaultValue = ""
                },
                navArgument(Destination.HubPhotos.ARG_READ_ONLY) {
                    type = NavType.BoolType
                    defaultValue = false
                },
            ),
    ) { entry ->
        val batchId = entry.arguments?.getString(Destination.HubPhotos.ARG_BATCH)?.ifEmpty { null }
        val readOnly = entry.arguments?.getBoolean(Destination.HubPhotos.ARG_READ_ONLY) ?: false
        val model: HubMediaViewModel =
            viewModel { HubMediaViewModel(HttpHubMediaApi(client, bucket), batchId, readOnly) }
        val state by model.state.collectAsState()
        val resolver = LocalContext.current.contentResolver
        val picker =
            rememberLauncherForActivityResult(PickVisualMedia()) { uri ->
                model.picked(uri?.let { pickedPhoto(resolver, it) })
            }
        LaunchedEffect(Unit) { model.load() }
        HubPhotosScreen(
            state = state,
            actions =
                HubPhotosActions(
                    onAltEn = model::editAltEn,
                    onAltBn = model::editAltBn,
                    onAdd = {
                        if (model.startPicking()) picker.launch(PickVisualMediaRequest(PickVisualMedia.ImageOnly))
                    },
                    onRetryUpload = model::retry,
                    onRetryLoad = model::retryLoad,
                    onMove = model::move,
                    onDelete = model::askDelete,
                    onConfirmDelete = model::confirmDelete,
                    onCancelDelete = model::cancelDelete,
                    onRetryWrite = model::retryWrite,
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}

/**
 * Guardian reviews and the owner's Reviews screen [H4]: the guardian's
 * list, opened from the guardian home's Reviews row; one batch's review,
 * opened from the list or a review-outcome inbox item; and the owner's
 * Reviews screen, opened from the listing editor's Reviews row or a
 * new-reviews inbox item, whose Report opens [Destination.HubReport] for
 * the review.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 */
private fun NavGraphBuilder.hubReviewsRoutes(client: HttpClient, navController: NavHostController) {
    composable(Destination.HubMyReviews.route) {
        val model: MyReviewsViewModel = viewModel { MyReviewsViewModel(HttpHubReviewsApi(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        MyReviewsScreen(
            state = state,
            actions =
                MyReviewsActions(
                    onOpen = { row ->
                        navController.navigate(Destination.HubReviewEditor.of(row.batchId, row.batchTitle))
                    },
                    onRetry = model::load,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(
        route = Destination.HubReviewEditor.route,
        arguments =
            listOf(
                navArgument(Destination.HubReviewEditor.ARG_BATCH) { type = NavType.StringType },
                navArgument(Destination.HubReviewEditor.ARG_TITLE) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
    ) { entry ->
        val batchId = entry.arguments?.getString(Destination.HubReviewEditor.ARG_BATCH).orEmpty()
        val title = entry.arguments?.getString(Destination.HubReviewEditor.ARG_TITLE)
        val model: ReviewEditorViewModel =
            viewModel(key = "hub-review/$batchId") { ReviewEditorViewModel(HttpHubReviewsApi(client), batchId) }
        val state by model.state.collectAsState()
        LaunchedEffect(batchId) { model.load() }
        ReviewEditorScreen(
            state = state,
            title = title,
            actions =
                ReviewEditorActions(
                    onRating = model::pickRating,
                    onText = model::editText,
                    onSave = model::save,
                    onDelete = model::askDelete,
                    onConfirmDelete = model::confirmDelete,
                    onCancelDelete = model::cancelDelete,
                    onRetry = model::retry,
                    onRetryLoad = model::retryLoad,
                    onDismissNotice = model::dismissNotice,
                    onBack = { navController.popBackStack() },
                ),
        )
    }

    composable(Destination.HubOwnerReviews.route) {
        val model: OwnerReviewsViewModel = viewModel { OwnerReviewsViewModel(HttpHubReviewsApi(client)) }
        val state by model.state.collectAsState()
        LaunchedEffect(Unit) { model.load() }
        OwnerReviewsScreen(
            state = state,
            actions =
                OwnerReviewsActions(
                    onReply = model::editReply,
                    onSend = model::sendReply,
                    onDelete = model::askDeleteReply,
                    onConfirmDelete = model::confirmDeleteReply,
                    onCancelDelete = model::cancelDeleteReply,
                    onRetry = model::retry,
                    // A review is reported by its id [T9-e].
                    onReport = { id -> navController.navigate(Destination.HubReport.of(ReportKind.REVIEW.wire, id)) },
                    onRetryLoad = model::retryLoad,
                    onDismissNotice = model::dismissNotice,
                    onBack = { navController.popBackStack() },
                ),
        )
    }
}

/**
 * Opens the report screen for a "Report this page" App Link, once there
 * is someone to report as.
 *
 * **Signed out, the link waits**: the graph starts at sign-in, and the
 * link stays pending in `MainActivity` (kept across a rotation in its
 * saved state) until the session is signed in and the graph is rebuilt
 * for it -- which is also after the choose-username gate and the lens
 * picker, since neither composes the graph. Then the screen is pushed
 * over the new home, so Back lands there, and the link is consumed so it
 * cannot open twice. The same shape as the inbox notification's
 * `OpenInboxEffect`.
 *
 * @param navController The app's controller
 * @param signedIn Whether a session exists
 * @param link The link waiting to be opened, or null
 * @param onOpened Called once the screen has been opened, to consume the link
 */
@Composable
internal fun HubReportLinkEffect(
    navController: NavController,
    signedIn: Boolean,
    link: ReportLink?,
    onOpened: () -> Unit,
) {
    LaunchedEffect(signedIn, link) {
        if (signedIn && link != null) {
            navController.navigate(Destination.HubReport.of(link.kind, link.id)) { launchSingleTop = true }
            onOpened()
        }
    }
}

/**
 * Opens the form for an "Ask to join" App Link, once there is someone to
 * ask as: the twin of [HubReportLinkEffect]. Signed out, the link waits in
 * `MainActivity` (kept across a rotation) until the session is signed in
 * and the graph is rebuilt for it; then the form is pushed over the new
 * home and the link is consumed so it cannot open twice.
 *
 * @param navController The app's controller
 * @param signedIn Whether a session exists
 * @param link The link waiting to be opened, or null
 * @param onOpened Called once the form has been opened, to consume the link
 */
@Composable
internal fun HubEnquiryLinkEffect(
    navController: NavController,
    signedIn: Boolean,
    link: EnquiryLink?,
    onOpened: () -> Unit,
) {
    LaunchedEffect(signedIn, link) {
        if (signedIn && link != null) {
            navController.navigate(Destination.HubEnquiryForm.of(link.owner, link.batch)) { launchSingleTop = true }
            onOpened()
        }
    }
}

/**
 * Open a public page in the phone's browser, outside the app.
 *
 * A phone with no browser shows nothing rather than crashing; the editor
 * is unchanged and the page is still public.
 *
 * @param context The activity context
 * @param url The page
 */
private fun openInBrowser(context: Context, url: String) {
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    } catch (_: ActivityNotFoundException) {
        // Nothing on this phone opens a web page.
    }
}
