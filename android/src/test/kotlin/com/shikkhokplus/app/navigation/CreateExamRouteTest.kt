package com.shikkhokplus.app.navigation

import androidx.compose.material3.Text
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.core.ui.TAG_FORM_NAME
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.HttpStatusCode
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

/**
 * "New exam" opened the way the app opens it: from the batch screen.
 *
 * **Reported from a device: the button crashed the app.** The form
 * looked up the standalone exam-list route as its parent, which nothing
 * navigates to since the batch screen's Exams tab replaced it, and
 * `getBackStackEntry` throws for a route that is not on the back stack.
 * A screen test of the form alone could not see this: the crash is in
 * the route, so the route is what this drives.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class CreateExamRouteTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `new exam opened from the batch screen shows the form`() {
        val client =
            ApiClient.build(
                "https://staging.example",
                MockEngine { respond("", HttpStatusCode.NotFound) },
                TokenStore.InMemory(),
            )
        val queue = QueueStore(File.createTempFile("queue", ".json").apply { deleteOnExit() })
        lateinit var nav: NavHostController

        compose.setContent {
            ShikkhokTheme {
                nav = rememberNavController()
                NavHost(nav, startDestination = HOME) {
                    composable(HOME) { Text("home") }
                    // Stands in for the batch screen, which is
                    // registered under this route.
                    composable(Destination.Roster.route) { Text("batch") }
                    teachingRoutes(client, queue, nav)
                }
            }
        }
        compose.runOnIdle {
            nav.navigate(Destination.Roster.of("b1", "Physics"))
            nav.navigate(Destination.CreateExam.of("b1"))
        }

        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithTag(TAG_FORM_NAME).fetchSemanticsNodes().isNotEmpty()
        }
    }

    private companion object {
        /** A plain start screen, so the batch route is navigated to with its arguments. */
        const val HOME = "home"
    }
}
