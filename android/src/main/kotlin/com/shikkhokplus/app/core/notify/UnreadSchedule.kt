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
    private const val KEY_LAST = "last_notified"
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
        saveLastNotified(context, 0)
    }

    /**
     * The count last told to the person.
     *
     * @param context Any context
     * @return The remembered count, zero when none
     */
    fun lastNotified(context: Context): Int =
        prefs(context).getInt(KEY_LAST, 0)

    /**
     * Remember the count just told to the person.
     *
     * @param context Any context
     * @param count The count
     */
    fun saveLastNotified(context: Context, count: Int) {
        prefs(context).edit().putInt(KEY_LAST, count).apply()
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
