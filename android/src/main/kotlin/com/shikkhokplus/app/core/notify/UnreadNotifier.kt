package com.shikkhokplus.app.core.notify

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.shikkhokplus.app.MainActivity
import com.shikkhokplus.app.R

/**
 * The one tray notification: how many updates are waiting.
 *
 * **The count is the server's.** This decides only whether to say it
 * again, by the newest unread item rather than by the count: a count
 * baseline missed a new item after the person had read the old ones in
 * the app (told 3, read 3, 1 arrives: 1 is not above 3). The newest
 * unread item's id is remembered instead, so a new item always posts and
 * the same items never post twice, whatever the count did in between.
 *
 * **The text names no person, batch or amount.** A lock screen is read
 * by whoever holds the phone, and a child's phone is often a parent's.
 *
 * @property context Any context; the application one is kept
 */
class UnreadNotifier(context: Context) {
    private val context: Context = context.applicationContext

    /**
     * Post, update or cancel the notification for a fresh read.
     *
     * Opening the app cancels the tray entry but keeps the remembered
     * item: the person has not necessarily read it, and telling them
     * again about the same items is the repeat this exists to prevent.
     *
     * @param unread The server's unread count
     * @param newestUnread The newest unread item's id, or null if none
     * @param lastNotified The newest item last told to the person
     * @return The item to remember as last notified, null when none is unread
     */
    fun update(unread: Int, newestUnread: String?, lastNotified: String?): String? {
        if (unread <= 0 || newestUnread == null) {
            cancel()
            return null
        }
        if (newestUnread != lastNotified) post(unread)
        return newestUnread
    }

    /** Remove the notification, if showing. */
    fun cancel() {
        NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID)
    }

    private fun canPost(): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.POST_NOTIFICATIONS,
            ) == PackageManager.PERMISSION_GRANTED

    private fun post(unread: Int) {
        if (!canPost()) return
        ensureChannel()
        val open =
            Intent(context, MainActivity::class.java)
                .putExtra(EXTRA_OPEN, OPEN_INBOX)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val tap =
            PendingIntent.getActivity(
                context,
                0,
                open,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        val notification =
            NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(context.getString(R.string.app_name))
                .setContentText(context.resources.getQuantityString(R.plurals.tray_updates, unread, unread))
                .setNumber(unread)
                .setOnlyAlertOnce(true)
                .setAutoCancel(true)
                .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
                .setContentIntent(tap)
                .build()
        try {
            NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, notification)
        } catch (_: SecurityException) {
            return
        }
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                context.getString(R.string.tray_channel_name),
                NotificationManager.IMPORTANCE_DEFAULT,
            ),
        )
    }

    companion object {
        const val NOTIFICATION_ID = 1001
        const val CHANNEL_ID = "updates"
        const val EXTRA_OPEN = "open"
        const val OPEN_INBOX = "inbox"

        /**
         * Whether a launch intent came from tapping the notification.
         *
         * @param intent The launch intent, if any
         * @return True when it asks for the inbox
         */
        fun wantsInbox(intent: Intent?): Boolean =
            intent?.getStringExtra(EXTRA_OPEN) == OPEN_INBOX

        /**
         * Whether a fresh launch should open the inbox. A recreated
         * activity (rotation) never does: the tap was already handled.
         *
         * @param intent The launch intent, if any
         * @param savedInstanceState The saved state, null on a first launch
         * @return True when the inbox should open
         */
        fun opensInboxOnCreate(intent: Intent?, savedInstanceState: Any?): Boolean =
            savedInstanceState == null && wantsInbox(intent)

        /**
         * Mark a tap handled so the same intent cannot open it again.
         *
         * @param intent The intent that carried the tap
         */
        fun consume(intent: Intent?) {
            intent?.removeExtra(EXTRA_OPEN)
        }
    }
}
