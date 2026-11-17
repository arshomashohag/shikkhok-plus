package com.shikkhokplus.app.navigation

import androidx.compose.material3.Text
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_SAVE
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.http.ContentType
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.util.Collections
import kotlin.test.assertEquals

/**
 * The listing editor's thana select, driven through the real route.
 *
 * **Found in review: the select was drawn and did nothing.** The route
 * built the screen's actions without the thana callback, so the action's
 * empty default swallowed every pick, while the view model's own test
 * called the view model directly and passed. The wiring lives in the
 * route, so the route is what this drives: a pick must reach the server.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class HubListingRouteTest {

    @get:Rule
    val compose = createComposeRule()

    private val json = headersOf("Content-Type", ContentType.Application.Json.toString())

    /** A saved listing in Mirpur, a thana of Dhaka North City Corporation. */
    private val listingJson =
        """{"status":"draft","public_name":"Rahima","teaching_mode":[],
        "district_code":"BD3026","upazila_code":"MT3026250003",
        "checklist":[],"publishable":false,"runs_classes":false,
        "consent_version_current":"2026-11-14","is_centre":false}"""

    private fun area(code: String, kind: String, name: String) =
        """{"code":"$code","kind":"$kind","name_en":"$name","name_bn":"$name"}"""

    /** The area tree, by parent; the empty key is the top level. */
    private val areas =
        mapOf(
            "" to listOf(area("BD30", "division", "Dhaka Division")),
            "BD30" to listOf(area("BD3026", "district", "Dhaka")),
            "BD3026" to
                listOf(
                    area("BD30260072", "upazila", "Savar"),
                    area("BD30262500", "city_corporation", "Dhaka North City Corporation"),
                ),
            "BD30262500" to
                listOf(
                    area("MT3026250003", "metro_thana", "Mirpur"),
                    area("MT3026250006", "metro_thana", "Uttara"),
                ),
        )

    @Test
    fun `choosing the whole city corporation in the thana select reaches the server`() {
        val saved = Collections.synchronizedList(mutableListOf<String>())
        val engine =
            MockEngine { request ->
                when {
                    request.url.encodedPath == "/v1/hub/areas" -> {
                        val parent = request.url.parameters["parent"].orEmpty()
                        respond(areas[parent].orEmpty().joinToString(",", "[", "]"), HttpStatusCode.OK, json)
                    }
                    request.method == HttpMethod.Put -> {
                        saved += (request.body as TextContent).text
                        respond(listingJson, HttpStatusCode.OK, json)
                    }
                    else -> respond(listingJson, HttpStatusCode.OK, json)
                }
            }
        val client = ApiClient.build("https://staging.example", engine, TokenStore.InMemory())
        lateinit var nav: NavHostController

        compose.setContent {
            ShikkhokTheme {
                nav = rememberNavController()
                NavHost(nav, startDestination = HOME) {
                    composable(HOME) { Text("home") }
                    hubRoutes(client, nav)
                }
            }
        }
        compose.runOnIdle { nav.navigate(Destination.HubListing.route) }

        // The saved thana reopens under its city corporation.
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithTag(THANA).fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag(THANA).performScrollTo().performClick()
        compose.onNodeWithText("Whole city corporation").performSemanticsAction(SemanticsActions.OnClick)
        compose.onNodeWithTag(TAG_HUB_SAVE).performScrollTo().performClick()

        compose.waitUntil(timeoutMillis = 5_000) { saved.isNotEmpty() }
        assertEquals(
            listOf("""{"district_code":"BD3026","upazila_code":"BD30262500"}"""),
            saved.toList(),
        )
    }

    private companion object {
        /** A plain start screen, so the listing route is navigated to. */
        const val HOME = "home"

        /** The thana select, tagged by its English label. */
        const val THANA = "hub_area_Thana (optional)"
    }
}
