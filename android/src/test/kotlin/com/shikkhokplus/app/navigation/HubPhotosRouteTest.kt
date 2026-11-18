package com.shikkhokplus.app.navigation

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import androidx.activity.compose.LocalActivityResultRegistryOwner
import androidx.activity.result.ActivityResultRegistry
import androidx.activity.result.ActivityResultRegistryOwner
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContract
import androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia
import androidx.compose.material3.Text
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextReplacement
import androidx.core.app.ActivityOptionsCompat
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.feature.hublisting.ui.TAG_BATCH_PHOTOS
import com.shikkhokplus.app.feature.hublisting.ui.TAG_HUB_PHOTOS
import com.shikkhokplus.app.feature.hublisting.ui.batchListingRowTag
import com.shikkhokplus.app.feature.hubmedia.BucketClient
import com.shikkhokplus.app.feature.hubmedia.ui.TAG_PHOTOS_ADD
import com.shikkhokplus.app.feature.hubmedia.ui.TAG_PHOTOS_ALT_BN
import com.shikkhokplus.app.feature.hubmedia.ui.TAG_PHOTOS_ALT_EN
import com.shikkhokplus.app.feature.hubmedia.ui.TAG_PHOTOS_COUNT
import com.shikkhokplus.app.feature.hubmedia.ui.TAG_PHOTOS_RETRY_LOAD
import com.shikkhokplus.app.feature.hubmedia.ui.TAG_PHOTOS_RETRY_UPLOAD
import com.shikkhokplus.app.feature.hubmedia.ui.TAG_PHOTO_DELETE_CONFIRM
import com.shikkhokplus.app.feature.hubmedia.ui.photoDeleteTag
import com.shikkhokplus.app.feature.hubmedia.ui.photoMoveUpTag
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.engine.mock.toByteArray
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
import io.ktor.http.content.TextContent
import io.ktor.http.headersOf
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.io.File
import java.io.IOException
import java.util.Collections
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The photo editor driven through the real routes, with one MockEngine
 * answering as both the API and the bucket.
 *
 * **Every action is reached the way a person reaches it**: the listing
 * and batch editors' Photos rows, the picker (through the activity-result
 * registry, so the real `PickVisualMedia(ImageOnly)` launch is what runs),
 * the content resolver's type and size, the presigned POST, `complete`,
 * reorder, delete and every retry. An earlier unit shipped an action the
 * screen drew and the route never wired; a view-model test cannot see
 * that, and this can.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1600dp")
class HubPhotosRouteTest {

    @get:Rule
    val compose = createComposeRule()

    private val json = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString())

    /** One request as the engine saw it: where, how, which headers, and the body. */
    private data class Seen(val method: HttpMethod, val url: String, val headers: Set<String>, val body: String)

    private val seen: MutableList<Seen> = Collections.synchronizedList(mutableListOf())

    /** What `GET /v1/hub/media` answers, changed by a test as the server would. */
    @Volatile
    private var gallery: String = "[]"

    /** Throw on the next `complete`, as a dropped connection does. */
    @Volatile
    private var dropNextComplete = false

    /** Throw on the next gallery read. */
    @Volatile
    private var dropNextList = false

    /** Every picker launch, with the request it carried. */
    private val launched = Collections.synchronizedList(mutableListOf<Any?>())

    @Before
    fun registerProvider() {
        PhotoProvider.throwing = null
        Robolectric.setupContentProvider(PhotoProvider::class.java, AUTHORITY)
    }

    private fun photo(id: String, position: Int, status: String = "approved", batchId: String? = null) =
        """{"id":"$id","batch_id":${batchId?.let { "\"$it\"" } ?: "null"},"status":"$status",
        "alt_en":"Photo $position","alt_bn":null,"position":$position,"width":960,"height":640,
        "rejection_code":null,"thumb_url":"https://site.example/m/key$position/320.webp"}"""

    private suspend fun MockRequestHandleScope.answer(request: HttpRequestData): HttpResponseData {
        val body =
            when (val content = request.body) {
                is TextContent -> content.text
                else -> String(content.toByteArray())
            }
        seen += Seen(request.method, request.url.toString(), request.headers.names(), body)
        return when {
            request.url.host == BUCKET_HOST -> respond("", HttpStatusCode.NoContent)
            request.url.encodedPath.startsWith("/v1/hub/media") -> media(request)
            else -> listings(request.url.encodedPath)
        }
    }

    /** The listing editors' reads. */
    private fun MockRequestHandleScope.listings(path: String): HttpResponseData =
        when (path) {
            "/v1/hub/listing" -> respond(LISTING, HttpStatusCode.OK, json)
            "/v1/hub/batch-listings" -> respond(BATCHES, HttpStatusCode.OK, json)
            else -> respond("[]", HttpStatusCode.OK, json)
        }

    /** The photo routes, dropping a connection where a test asked for one. */
    private fun MockRequestHandleScope.media(request: HttpRequestData): HttpResponseData {
        val path = request.url.encodedPath
        return when {
            path == "/v1/hub/media" -> {
                if (dropNextList) {
                    dropNextList = false
                    throw IOException("dropped")
                }
                respond(gallery, HttpStatusCode.OK, json)
            }
            path == "/v1/hub/media/uploads" -> respond(TICKET, HttpStatusCode.OK, json)
            path.endsWith("/complete") -> {
                if (dropNextComplete) {
                    dropNextComplete = false
                    throw IOException("dropped")
                }
                respond(photo(PHOTO_A, 2, status = "pending_review"), HttpStatusCode.OK, json)
            }
            path == "/v1/hub/media/order" -> respond(REORDERED, HttpStatusCode.OK, json)
            else -> respond("", HttpStatusCode.NoContent)
        }
    }

    private fun host(start: String): NavHostController {
        val engine = MockEngine { answer(it) }
        val tokens = TokenStore.InMemory().apply { save("access-1", "refresh-1") }
        val client = ApiClient.build("https://staging.example", engine, tokens)
        val bucket = BucketClient.build(engine)
        val registry =
            object : ActivityResultRegistry() {
                override fun <I, O> onLaunch(
                    requestCode: Int,
                    contract: ActivityResultContract<I, O>,
                    input: I,
                    options: ActivityOptionsCompat?,
                ) {
                    launched += input
                    dispatchResult(requestCode, PHOTO_URI)
                }
            }
        val owner = object : ActivityResultRegistryOwner {
            override val activityResultRegistry: ActivityResultRegistry = registry
        }
        lateinit var nav: NavHostController
        compose.setContent {
            CompositionLocalProvider(LocalActivityResultRegistryOwner provides owner) {
                ShikkhokTheme {
                    nav = rememberNavController()
                    NavHost(nav, startDestination = HOME) {
                        composable(HOME) { Text("home") }
                        hubRoutes(client, nav, bucket = bucket)
                    }
                }
            }
        }
        compose.runOnIdle { nav.navigate(start) }
        return nav
    }

    private fun waitForTag(tag: String) =
        compose.waitUntil(timeoutMillis = 5_000) { compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty() }

    private fun waitForText(text: String) =
        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
        }

    private fun requests(method: HttpMethod, needle: String) = seen.filter { it.method == method && needle in it.url }

    private fun typeAltsAndChoose() {
        compose.onNodeWithTag(TAG_PHOTOS_ALT_EN).performScrollTo().performTextReplacement("A class")
        compose.onNodeWithTag(TAG_PHOTOS_ALT_BN).performScrollTo().performTextReplacement("ক্লাস")
        compose.onNodeWithTag(TAG_PHOTOS_ADD).performScrollTo().performClick()
    }

    @Test
    fun `the listing's Photos row uploads through the presigned form, then reorders and deletes`() {
        gallery = "[${photo(PHOTO_B, 1)}]"
        val nav = host(Destination.HubListing.route)

        waitForTag(TAG_HUB_PHOTOS)
        compose.onNodeWithTag(TAG_HUB_PHOTOS).performScrollTo().performClick()
        waitForTag(TAG_PHOTOS_ADD)
        assertEquals(Destination.HubPhotos.route, nav.currentDestination?.route)
        waitForText("1 of 12 photos")

        typeAltsAndChoose()
        waitForText("Awaiting review")

        // The picker was asked for images only, which needs no permission.
        val request = assertIs<PickVisualMediaRequest>(launched.single())
        assertEquals(PickVisualMedia.ImageOnly, request.mediaType)

        // The declared type and size are the content resolver's.
        assertEquals(
            """{"content_type":"image/png","byte_size":${PNG.size}}""",
            requests(HttpMethod.Post, "/v1/hub/media/uploads").single().body,
        )

        val post = requests(HttpMethod.Post, BUCKET_HOST).single()
        assertEquals(BUCKET_URL, post.url)
        // The bucket is never sent the session token, nor the app's own headers.
        assertTrue(HttpHeaders.Authorization !in post.headers, "headers: ${post.headers}")
        assertTrue("X-Client-Platform" !in post.headers, "headers: ${post.headers}")
        // The ticket's fields first, in their order, and the file last.
        // Each part's raw Content-Disposition, and every name a quoted-string (RFC 7578).
        val dispositions =
            Regex("""Content-Disposition: ([^\r\n]+)""").findAll(post.body).map { it.groupValues[1] }.toList()
        assertEquals(
            listOf(
                "form-data; name=\"key\"",
                "form-data; name=\"Content-Type\"",
                "form-data; name=\"policy\"",
                "form-data; name=\"x-amz-signature\"",
                "form-data; name=\"file\"; filename=\"photo\"",
            ),
            dispositions,
        )
        assertTrue(String(PNG) in post.body, "the file's bytes are posted")
        // The API, unlike the bucket, carries the session.
        assertTrue(HttpHeaders.Authorization in requests(HttpMethod.Post, "/v1/hub/media/uploads").single().headers)

        assertEquals(
            """{"alt_en":"A class","alt_bn":"ক্লাস"}""",
            requests(HttpMethod.Post, "/v1/hub/media/$PHOTO_A/complete").single().body,
        )
        compose.onNodeWithTag(TAG_PHOTOS_COUNT).assertExists()
        waitForText("2 of 12 photos")

        // Move the new photo up: the ids go in their new order.
        compose.onNodeWithTag(photoMoveUpTag(1)).performScrollTo().performClick()
        compose.waitUntil(timeoutMillis = 5_000) { requests(HttpMethod.Put, "/v1/hub/media/order").isNotEmpty() }
        assertEquals(
            """{"ids":["$PHOTO_A","$PHOTO_B"]}""",
            requests(HttpMethod.Put, "/v1/hub/media/order").single().body,
        )

        // Delete asks first, then deletes.
        compose.onNodeWithTag(photoDeleteTag(0)).performScrollTo().performClick()
        assertTrue(requests(HttpMethod.Delete, "/v1/hub/media/").isEmpty())
        waitForTag(TAG_PHOTO_DELETE_CONFIRM)
        compose.onNodeWithTag(TAG_PHOTO_DELETE_CONFIRM).performSemanticsAction(SemanticsActions.OnClick)
        compose.waitUntil(timeoutMillis = 5_000) { requests(HttpMethod.Delete, "/v1/hub/media/").isNotEmpty() }
        assertEquals("https://staging.example/v1/hub/media/$PHOTO_A", requests(HttpMethod.Delete, "/v1/").single().url)
        waitForText("1 of 12 photos")
    }

    @Test
    fun `a dropped connection is retried through the route, and the file is posted once`() {
        dropNextList = true
        host(Destination.HubPhotos.of(null, readOnly = false))

        waitForTag(TAG_PHOTOS_RETRY_LOAD)
        compose.onNodeWithTag(TAG_PHOTOS_RETRY_LOAD).performScrollTo().performClick()
        waitForText("0 of 12 photos")

        dropNextComplete = true
        typeAltsAndChoose()
        waitForTag(TAG_PHOTOS_RETRY_UPLOAD)
        compose.onNodeWithTag(TAG_PHOTOS_RETRY_UPLOAD).performScrollTo().performClick()
        waitForText("Awaiting review")

        assertEquals(1, requests(HttpMethod.Post, BUCKET_HOST).size)
        assertEquals(2, requests(HttpMethod.Post, "/complete").size)
        assertEquals(2, requests(HttpMethod.Get, "/v1/hub/media").size)
    }

    @Test
    fun `the batch editor's Photos row opens that batch's gallery of eight, and Back returns`() {
        val nav = host(Destination.BatchListings.route)

        waitForTag(batchListingRowTag(BATCH))
        compose.onNodeWithTag(batchListingRowTag(BATCH)).performClick()
        waitForTag(TAG_BATCH_PHOTOS)
        compose.onNodeWithTag(TAG_BATCH_PHOTOS).performSemanticsAction(SemanticsActions.OnClick)

        waitForText("0 of 8 photos")
        assertEquals(Destination.HubPhotos.route, nav.currentDestination?.route)
        val read = requests(HttpMethod.Get, "/v1/hub/media").single()
        assertEquals("https://staging.example/v1/hub/media?batch_id=$BATCH", read.url)

        compose.onNodeWithContentDescription("Back").performClick()
        compose.waitForIdle()
        assertEquals(Destination.BatchListings.route, nav.currentDestination?.route)
    }

    @Test
    fun `a provider that will not say the size still uploads, measured from the bytes`() {
        PhotoProvider.throwing = PhotoProvider.Failing.QUERY
        host(Destination.HubPhotos.of(null, readOnly = false))
        waitForText("0 of 12 photos")

        typeAltsAndChoose()
        waitForText("Awaiting review")

        assertEquals(
            """{"content_type":"image/png","byte_size":${PNG.size}}""",
            requests(HttpMethod.Post, "/v1/hub/media/uploads").single().body,
        )
    }

    @Test
    fun `a provider that throws on the file is refused in words, not a crash`() {
        PhotoProvider.throwing = PhotoProvider.Failing.OPEN_FILE
        host(Destination.HubPhotos.of(null, readOnly = false))
        waitForText("0 of 12 photos")

        typeAltsAndChoose()
        waitForText("This file could not be read as a photo. Choose another.")

        assertTrue(requests(HttpMethod.Post, "/v1/hub/media/uploads").isEmpty())
        compose.onNodeWithTag(TAG_PHOTOS_ADD).assertIsEnabled()
    }

    @Test
    fun `a provider that throws on the type is refused as a type the server does not take`() {
        PhotoProvider.throwing = PhotoProvider.Failing.TYPE
        host(Destination.HubPhotos.of(null, readOnly = false))
        waitForText("0 of 12 photos")

        typeAltsAndChoose()
        waitForText("Choose a JPEG, PNG or WebP photo.")

        assertTrue(requests(HttpMethod.Post, "/v1/hub/media/uploads").isEmpty())
    }

    @Test
    fun `a suspended batch opens its gallery read-only`() {
        host(Destination.HubPhotos.of(BATCH, readOnly = true))
        waitForText("0 of 8 photos")
        assertTrue(compose.onAllNodesWithTag(TAG_PHOTOS_ADD).fetchSemanticsNodes().isEmpty())
        assertNull(launched.firstOrNull())
    }

    /** A picked photo: a content URI with a type, a size and bytes, as the photo picker hands back. */
    class PhotoProvider : ContentProvider() {
        /** Which provider call throws, as a cloud document provider may. */
        enum class Failing { TYPE, QUERY, OPEN_FILE }

        companion object {
            /** The call that throws in this test, or null for a provider that answers. */
            @Volatile
            var throwing: Failing? = null
        }

        override fun onCreate(): Boolean = true

        override fun getType(uri: Uri): String {
            if (throwing == Failing.TYPE) throw UnsupportedOperationException("no type")
            return "image/png"
        }

        override fun query(
            uri: Uri,
            projection: Array<out String>?,
            selection: String?,
            selectionArgs: Array<out String>?,
            sortOrder: String?,
        ): Cursor {
            if (throwing == Failing.QUERY) throw SecurityException("no query")
            return MatrixCursor(arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE)).apply {
                addRow(arrayOf<Any>("class.png", PNG.size.toLong()))
            }
        }

        override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
            check(throwing != Failing.OPEN_FILE) { "document gone" }
            val file = File.createTempFile("photo", ".png").apply { writeBytes(PNG) }
            return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
        }

        override fun insert(uri: Uri, values: ContentValues?): Uri? = null

        override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int = 0

        override fun update(
            uri: Uri,
            values: ContentValues?,
            selection: String?,
            selectionArgs: Array<out String>?,
        ): Int = 0
    }

    private companion object {
        const val HOME = "home"
        const val AUTHORITY = "com.shikkhokplus.test.photos"
        val PHOTO_URI: Uri = Uri.parse("content://$AUTHORITY/photo/1")
        val PNG: ByteArray = "PNG-BYTES-0123456789".toByteArray()

        const val PHOTO_A = "a1111111-1111-4111-8111-111111111111"
        const val PHOTO_B = "b2222222-2222-4222-8222-222222222222"
        const val BATCH = "0b9e8d7c-6b5a-4c3d-9e2f-1a0b9c8d7e6f"

        const val BUCKET_HOST = "bucket.example"
        const val BUCKET_URL = "https://$BUCKET_HOST/"

        val TICKET =
            """{"media_id":"$PHOTO_A","url":"$BUCKET_URL",
            "fields":{"key":"quarantine/$PHOTO_A","Content-Type":"image/png","policy":"p","x-amz-signature":"s"},
            "expires_at":"2026-11-18T10:10:00Z"}"""

        const val LISTING =
            """{"status":"draft","public_name":"Rahima","teaching_mode":[],"checklist":[],"publishable":false,
            "runs_classes":false,"consent_version_current":"2026-11-14","is_centre":false}"""

        val REORDERED =
            """[{"id":"$PHOTO_A","status":"approved","alt_en":"Photo 1","position":1},
            {"id":"$PHOTO_B","status":"approved","alt_en":"Photo 2","position":2}]"""

        const val BATCHES =
            """[{"batch_id":"$BATCH","batch_name":"Physics 9","subjects":["Physics"],"status":"draft"}]"""
    }
}
