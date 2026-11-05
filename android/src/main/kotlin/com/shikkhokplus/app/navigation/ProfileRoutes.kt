package com.shikkhokplus.app.navigation

import androidx.compose.ui.platform.LocalContext
import android.net.Uri
import android.content.Intent
import com.shikkhokplus.app.BuildConfig
import com.shikkhokplus.app.feature.settings.ui.SettingsScreen
import com.shikkhokplus.app.core.settings.SettingsHolder
import androidx.activity.compose.BackHandler
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import com.shikkhokplus.app.core.network.HttpGuardianRepository
import com.shikkhokplus.app.core.network.HttpProfileRepository
import com.shikkhokplus.app.core.session.Lens
import com.shikkhokplus.app.feature.guardian.GuardianViewModel
import com.shikkhokplus.app.feature.guardian.ui.MyChildrenScreen
import com.shikkhokplus.app.feature.profile.ProfileUiState
import com.shikkhokplus.app.feature.profile.ProfileViewModel
import com.shikkhokplus.app.feature.profile.ui.EditProfileScreen
import io.ktor.client.HttpClient

/**
 * The screens pushed over More: Edit profile (S4) and a guardian's
 * children (G4).
 *
 * **Their own file for the reason the other route groups have one**: a
 * NavHost is one declarative tree, and these two carry the branching of
 * borrowing a ViewModel from an entry further down the stack, which
 * would otherwise push the host's complexity past detekt's bound.
 *
 * @param client The authenticated HTTP client
 * @param navController The app's controller
 * @param lens The lens in use, for the tab a chosen child returns to
 * @param settings This phone's preferences, or null when none are kept
 */
internal fun NavGraphBuilder.profileRoutes(
    client: HttpClient,
    navController: NavHostController,
    lens: Lens?,
    settings: SettingsHolder? = null,
) {
    if (settings != null) {
        composable(Destination.Settings.route) {
            val chosen by settings.state.collectAsState()
            val context = LocalContext.current
            SettingsScreen(
                settings = chosen,
                onChange = { next -> settings.update { next } },
                onBack = { navController.popBackStack() },
                supportPhone = BuildConfig.SUPPORT_PHONE.ifBlank { null },
                // The dialler, with the number filled in: the person
                // presses call. No calling permission is asked for.
                onCallForHelp = { number ->
                    runCatching {
                        context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number")))
                    }
                },
            )
        }
    }

    composable(Destination.EditProfile.route) { entry ->
        // The PROFILE's ViewModel, so More underneath shows the save
        // the moment the server confirms it.
        val parent =
            remember(entry) { navController.getBackStackEntry(Destination.Profile.route) }
        val model: ProfileViewModel =
            viewModel(parent) { ProfileViewModel(HttpProfileRepository(client)) }
        val state by model.state.collectAsState()
        val summary by model.summary.collectAsState()
        val close = {
            model.cancelEdit()
            navController.popBackStack()
            Unit
        }

        // A confirmed save closes the form; More shows "Saved.".
        LaunchedEffect(state) {
            if (state is ProfileUiState.Saved) navController.popBackStack()
        }
        BackHandler(onBack = close)

        EditProfileScreen(
            state = state,
            phone = summary?.phone,
            onSave = { name, address -> model.save(name, address) },
            onClose = close,
            onRetry = model::retry,
        )
    }

    composable(Destination.MyChildren.route) { entry ->
        // **The home screen's ViewModel when it is on the stack**, so
        // choosing a child here selects that child there [BR4.2]. The
        // guardian's home is the start of their graph, so it normally
        // is; a fresh one is the fallback, never a crash.
        val home =
            remember(entry) {
                runCatching { navController.getBackStackEntry(Destination.GuardianHome.route) }.getOrNull()
            }
        val model: GuardianViewModel =
            if (home != null) {
                viewModel(home) { GuardianViewModel(HttpGuardianRepository(client)) }
            } else {
                viewModel { GuardianViewModel(HttpGuardianRepository(client)) }
            }
        val state by model.state.collectAsState()
        val profile =
            remember(entry) {
                runCatching { navController.getBackStackEntry(Destination.Profile.route) }.getOrNull()
            }
        val phone =
            profile?.let {
                val owner: ProfileViewModel = viewModel(it) { ProfileViewModel(HttpProfileRepository(client)) }
                owner.summary.collectAsState().value?.phone
            }

        LaunchedEffect(Unit) { model.load() }

        MyChildrenScreen(
            state = state,
            phone = phone,
            onBack = { navController.popBackStack() },
            onChild = { index ->
                model.select(index)
                navController.switchTab(0, lens)
            },
            onRetry = model::retry,
        )
    }
}
