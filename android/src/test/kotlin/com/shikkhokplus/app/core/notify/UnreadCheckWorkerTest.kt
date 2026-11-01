package com.shikkhokplus.app.core.notify

import android.app.Application
import android.app.NotificationManager
import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.work.ListenableWorker
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.testing.WorkManagerTestInitHelper
import com.shikkhokplus.app.core.network.ApiClient
import kotlin.test.assertTrue
import androidx.work.testing.TestListenableWorkerBuilder
import com.shikkhokplus.app.core.network.TokenStore
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.headersOf
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull

/**
 * The background check reads the count and hands it to the notifier.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class UnreadCheckWorkerTest {
    private lateinit var context: Application
    private var requests = 0

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        shadowOf(context).grantPermissions("android.permission.POST_NOTIFICATIONS")
        requests = 0
    }

    @After
    fun tearDown() {
        UnreadCheckWorker.tokenStoreFactory = null
        UnreadCheckWorker.clientFactory = null
        AppForeground.visible = false
    }

    private fun signedIn(): TokenStore =
        TokenStore.InMemory().also { it.save("a", "r") }

    private fun item(id: String, read: Boolean = false) =
        """{"notification_id":"$id","kind":"notice","batch_name":"Physics",""" +
            """"created_at":"2026-10-17T06:00:00Z","read":$read}"""

    private fun serving(unread: Int, newest: String = "n-1", items: List<String>? = null) {
        val body = (items ?: List(unread) { item(if (it == 0) newest else "n-old-$it") }).joinToString(",")
        UnreadCheckWorker.tokenStoreFactory = { signedIn() }
        UnreadCheckWorker.clientFactory = { _, _ ->
            HttpClient(
                MockEngine {
                    requests++
                    respond(
                        """{"items":[$body],"unread":$unread}""",
                        headers = headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                    )
                },
            ) {
                install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
            }
        }
    }

    private fun run(): ListenableWorker.Result =
        runBlocking { TestListenableWorkerBuilder<UnreadCheckWorker>(context).build().doWork() }

    private fun posted() =
        shadowOf(context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .getNotification(UnreadNotifier.NOTIFICATION_ID)

    @Test
    fun `no token does nothing and makes no request`() {
        UnreadCheckWorker.tokenStoreFactory = { TokenStore.InMemory() }
        serving(3)
        UnreadCheckWorker.tokenStoreFactory = { TokenStore.InMemory() }
        assertEquals(ListenableWorker.Result.success(), run())
        assertEquals(0, requests)
        assertNull(posted())
    }

    @Test
    fun `a signed-in check posts the server's count and remembers it`() {
        serving(3)
        assertEquals(ListenableWorker.Result.success(), run())
        assertEquals(3, posted()!!.number)
        assertEquals("n-1", UnreadSchedule.lastNotified(context))
        assertEquals(ListenableWorker.Result.success(), run())
        assertNotNull(posted())
        assertEquals(2, requests)
    }

    @Test
    fun `the same items are not posted twice, even after the app cleared the tray`() {
        serving(3)
        run()
        UnreadNotifier(context).cancel()

        run()

        assertNull(posted())
        assertEquals("n-1", UnreadSchedule.lastNotified(context))
    }

    @Test
    fun `three told, all read in the app, then one new item posts`() {
        serving(3, newest = "n-3")
        run()
        UnreadNotifier(context).cancel()

        serving(1, items = listOf(item("n-4"), item("n-3", read = true)))
        run()

        assertEquals(1, posted()!!.number)
        assertEquals("n-4", UnreadSchedule.lastNotified(context))
    }

    @Test
    fun `a failed request leaves the baseline alone`() {
        UnreadCheckWorker.tokenStoreFactory = { signedIn() }
        UnreadCheckWorker.clientFactory = { _, _ ->
            HttpClient(MockEngine { respond("", io.ktor.http.HttpStatusCode.InternalServerError) })
        }
        assertEquals(ListenableWorker.Result.success(), run())
        assertNull(UnreadSchedule.lastNotified(context))
        assertNull(posted())
    }

    @Test
    fun `nothing runs while the app is on screen`() {
        serving(3)
        AppForeground.visible = true
        assertEquals(ListenableWorker.Result.success(), run())
        assertEquals(0, requests)
        assertNull(posted())
    }

    @Test
    fun `a refused renewal stops the schedule and clears the tray`() {
        WorkManagerTestInitHelper.initializeTestWorkManager(context)
        UnreadSchedule.start(context)
        UnreadNotifier(context).update(4, "n-4", null)
        UnreadSchedule.saveLastNotified(context, "n-4")
        val tokens = signedIn()
        UnreadCheckWorker.tokenStoreFactory = { tokens }
        UnreadCheckWorker.clientFactory = { store, ended ->
            ApiClient.build(
                "https://staging.example",
                MockEngine {
                    respond(
                        """{"error":{"code":"X","message_key":"auth.token.not_valid","retryable":false}}""",
                        io.ktor.http.HttpStatusCode.Unauthorized,
                        headersOf(HttpHeaders.ContentType, ContentType.Application.Json.toString()),
                    )
                },
                store,
                ended,
            )
        }

        assertEquals(ListenableWorker.Result.success(), run())

        val infos = WorkManager.getInstance(context).getWorkInfosForUniqueWork(UnreadSchedule.WORK_NAME).get()
        assertTrue(infos.all { it.state == WorkInfo.State.CANCELLED })
        assertNull(posted())
        assertNull(UnreadSchedule.lastNotified(context))
        assertNull(tokens.accessToken())
    }
}
