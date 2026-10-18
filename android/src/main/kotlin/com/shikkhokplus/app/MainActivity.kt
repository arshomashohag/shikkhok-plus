package com.shikkhokplus.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.lifecycle.viewmodel.compose.viewModel
import com.shikkhokplus.app.feature.auth.AuthRepository
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.auth.AuthViewModel
import com.shikkhokplus.app.feature.auth.ui.AuthScreen
import com.shikkhokplus.app.core.network.IssueResponse
import com.shikkhokplus.app.core.network.TokenResponse

/**
 * The single Activity. Screen one is OTP entry.
 *
 * **The skeleton's device leg.** This is what a human points a phone at
 * to verify that a Compose screen reaches a real FastAPI endpoint
 * against a real database — the thing a passing test suite cannot
 * demonstrate.
 *
 * The repository wired here is a placeholder returning a transport
 * failure, because the HTTP client lands with the Bolt that configures
 * the base URL per environment. **That is deliberate and visible**: the
 * screen renders its offline state rather than pretending to succeed,
 * so nothing here can be mistaken for a working network path.
 */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface {
                    val repository = remember { UnconfiguredRepository() }
                    val model: AuthViewModel = viewModel {
                        AuthViewModel(repository)
                    }
                    val state by model.state.collectAsState()

                    AuthScreen(
                        state = state,
                        onRequestCode = model::requestCode,
                        onSubmitCode = model::submitCode,
                        onRetry = model::retry,
                    )
                }
            }
        }
    }
}

/**
 * Stands in until the HTTP client is configured.
 *
 * Returns a transport failure rather than a fabricated success, so the
 * screen shows its offline state. A stub returning a fake token would
 * make the device run demonstrate nothing while looking like it worked.
 */
private class UnconfiguredRepository : AuthRepository {
    override suspend fun issue(phone: String): AuthResult<IssueResponse> =
        AuthResult.TransportFailure

    override suspend fun verify(
        phone: String,
        code: String,
    ): AuthResult<TokenResponse> = AuthResult.TransportFailure
}
