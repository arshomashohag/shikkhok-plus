package com.shikkhokplus.app.core.notify.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import androidx.navigation.NavController
import com.shikkhokplus.app.core.notify.UnreadNotifier
import com.shikkhokplus.app.core.notify.UnreadSchedule
import com.shikkhokplus.app.navigation.Destination

/**
 * Runs the unread check while signed in, asks for the notification
 * permission once, and clears the tray entry when the app comes forward.
 *
 * @param signedIn Whether a session is open
 */
@Composable
fun UnreadCheckEffects(signedIn: Boolean) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val askPermission =
        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(signedIn) {
        if (signedIn) {
            UnreadSchedule.start(context)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                !UnreadSchedule.permissionAsked(context)
            ) {
                UnreadSchedule.markPermissionAsked(context)
                askPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
            lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
                UnreadNotifier(context).cancel()
            }
        }
    }
}

/**
 * Opens the inbox once when a tray tap asked for it.
 *
 * @param navController The session's controller
 * @param requested Whether a tap asked for the inbox and someone is signed in
 * @param onOpened Called once the request has been handled
 */
@Composable
fun OpenInboxEffect(
    navController: NavController,
    requested: Boolean,
    onOpened: () -> Unit,
) {
    LaunchedEffect(requested) {
        if (requested) {
            val route = Destination.Inbox.route
            if (navController.graph.findNode(route) != null) navController.navigate(route) { launchSingleTop = true }
            onOpened()
        }
    }
}
