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
 * again: a notification already showing that number is not re-posted,
 * so a phone does not buzz every fifteen minutes for the same unread.
 *
 * **The text names no person, batch or amount.** A lock screen is read
 * by whoever holds the phone, and a child's phone is often a parent's.
 *
 * @property context Any context; the application one is kept
 */
class UnreadNotifier(context: Context) {
    private val context: Context = context.applicationContext

    /**
     * Post, update or cancel the notification for a fresh count.
     *
     * @param unread The server's unread count
     * @param lastNotified The count last told to the person
     * @return The count to remember as last notified
     */
    fun update(unread: Int, lastNotified: Int): Int {
        if (unread <= 0) {
            cancel()
            return 0
        }
        if (unread > lastNotified) post(unread)
        return unread
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
                .setContentText(context.getString(R.string.tray_updates, unread))
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
    }
}
