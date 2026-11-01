package com.shikkhokplus.app.core.notify

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/**
 * When the unread check runs, and what it remembers between runs.
 *
 * Fifteen minutes is WorkManager's floor for periodic work, not a
 * choice: the app icon count is therefore at most that stale.
 */
object UnreadSchedule {
    const val WORK_NAME = "unread-check"
    private const val PERIOD_MINUTES = 15L
    private const val PREFS = "unread"
    private const val KEY_LAST = "last_notified_item"
    private const val KEY_ASKED = "permission_asked"

    /**
     * Start the periodic check, keeping one already scheduled.
     *
     * @param context Any context
     */
    fun start(context: Context) {
        val request =
            PeriodicWorkRequestBuilder<UnreadCheckWorker>(PERIOD_MINUTES, TimeUnit.MINUTES)
                .setConstraints(
                    Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build(),
                )
                .build()
        WorkManager.getInstance(context.applicationContext).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request,
        )
    }

    /**
     * Stop the check and clear what it showed, at sign-out.
     *
     * @param context Any context
     */
    fun stop(context: Context) {
        WorkManager.getInstance(context.applicationContext).cancelUniqueWork(WORK_NAME)
        UnreadNotifier(context).cancel()
        saveLastNotified(context, null)
    }

    /**
     * The newest unread item last told to the person.
     *
     * @param context Any context
     * @return The remembered item's id, null when none
     */
    fun lastNotified(context: Context): String? =
        prefs(context).getString(KEY_LAST, null)

    /**
     * Remember the newest unread item just told to the person.
     *
     * @param context Any context
     * @param notificationId The item's id, or null to forget it
     */
    fun saveLastNotified(context: Context, notificationId: String?) {
        prefs(context).edit().putString(KEY_LAST, notificationId).apply()
    }

    /**
     * Whether the notification permission was already asked for.
     *
     * @param context Any context
     * @return True once asked, granted or refused
     */
    fun permissionAsked(context: Context): Boolean =
        prefs(context).getBoolean(KEY_ASKED, false)

    /**
     * Remember that the permission was asked for, so it is asked once.
     *
     * @param context Any context
     */
    fun markPermissionAsked(context: Context) {
        prefs(context).edit().putBoolean(KEY_ASKED, true).apply()
    }

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
