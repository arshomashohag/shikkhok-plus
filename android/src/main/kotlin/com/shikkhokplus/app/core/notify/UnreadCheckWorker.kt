package com.shikkhokplus.app.core.notify

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.shikkhokplus.app.BuildConfig
import com.shikkhokplus.app.core.network.ApiClient
import com.shikkhokplus.app.core.network.EncryptedTokenStore
import com.shikkhokplus.app.core.network.HttpInboxRepository
import com.shikkhokplus.app.core.network.TokenStore
import com.shikkhokplus.app.feature.auth.AuthResult
import io.ktor.client.HttpClient

/**
 * Reads the unread count in the background and tells the notifier.
 *
 * Signed out (no stored token) it does nothing and makes no request.
 * Any failure ends quietly with success: the next period tries again,
 * and a retry loop here would only spend the battery.
 */
class UnreadCheckWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val tokens = (tokenStoreFactory ?: { EncryptedTokenStore.create(it) })(applicationContext)
        if (tokens.accessToken() == null || AppForeground.visible) return Result.success()

        val client =
            (clientFactory ?: { store, ended ->
                ApiClient.build(BuildConfig.API_BASE_URL, tokenStore = store, onSessionEnded = ended)
            })(tokens) { UnreadSchedule.stop(applicationContext) }
        try {
            val result = HttpInboxRepository(client).inbox()
            if (result is AuthResult.Ok) {
                val last = UnreadSchedule.lastNotified(applicationContext)
                val next = UnreadNotifier(applicationContext).update(result.value.unread, last)
                UnreadSchedule.saveLastNotified(applicationContext, next)
            }
        } finally {
            client.close()
        }
        return Result.success()
    }

    companion object {
        internal var tokenStoreFactory: ((Context) -> TokenStore)? = null
        internal var clientFactory: ((TokenStore, () -> Unit) -> HttpClient)? = null
    }
}
