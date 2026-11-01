package com.shikkhokplus.app.navigation

import androidx.activity.ComponentActivity
import androidx.compose.material3.Text
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.core.queue.QueueStore
import com.shikkhokplus.app.feature.inbox.ui.TAG_INBOX_BADGE
import com.shikkhokplus.app.feature.inbox.ui.TAG_INBOX_BELL
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File

/**
 * A teacher's home tabs carry the bell: "a new payment to verify" lands
 * in the teacher's inbox, and without a bell there was no way to read it.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TeacherBellTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    @get:Rule
    val folder = TemporaryFolder()

    private val client =
        ApiClient.build(
            "https://staging.example",
            MockEngine { request ->
                if (request.url.encodedPath == "/v1/me/notifications") {
                    respond(
                        """{"items":[],"unread":2}""",
                        HttpStatusCode.OK,
                        headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                    )
                } else {
                    respond("", HttpStatusCode.ServiceUnavailable)
                }
            },
            TokenStore.InMemory().apply { save("a", "r") },
        )

    private fun opens(start: String) {
        compose.setContent {
            val nav = rememberNavController()
            NavHost(nav, startDestination = start) {
                todayRoute(client, QueueStore(File(folder.root, QueueStore.FILE_NAME)), nav, onOpenDues = {}) {}
                batchesRoute(client, nav) {}
                composable(Destination.Inbox.route) { Text("inbox opened") }
            }
        }

        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithTag(TAG_INBOX_BADGE, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag(TAG_INBOX_BELL).assertIsDisplayed()
        compose.onNodeWithTag(TAG_INBOX_BELL).performClick()
        compose.waitForIdle()
        compose.onNodeWithText("inbox opened").assertExists()
    }

    @Test
    fun `Today shows the bell with the server's count, and it opens the inbox`() = opens(Destination.Today.route)

    @Test
    fun `Batches shows the bell with the server's count, and it opens the inbox`() =
        opens(Destination.Batches.route)
}
