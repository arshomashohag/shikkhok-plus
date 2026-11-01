package com.shikkhokplus.app.core.notify

import android.app.Application
import android.app.NotificationManager
import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The tray notification posts on a rise and says nothing otherwise.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class UnreadNotifierTest {
    private lateinit var context: Application
    private lateinit var notifier: UnreadNotifier
    private lateinit var manager: NotificationManager

    @Before
    fun setUp() {
        context = ApplicationProvider.getApplicationContext()
        shadowOf(context).grantPermissions("android.permission.POST_NOTIFICATIONS")
        notifier = UnreadNotifier(context)
        manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    }

    private fun posted() = shadowOf(manager).getNotification(UnreadNotifier.NOTIFICATION_ID)

    @Test
    fun `first unread posts with the count as the number`() {
        assertEquals(3, notifier.update(3, 0))
        assertEquals(3, posted()!!.number)
    }

    @Test
    fun `an unchanged count posts nothing`() {
        assertEquals(3, notifier.update(3, 3))
        assertNull(posted())
    }

    @Test
    fun `a rise updates to the new count`() {
        notifier.update(3, 0)
        assertEquals(5, notifier.update(5, 3))
        assertEquals(5, posted()!!.number)
    }

    @Test
    fun `reading everything cancels the notification`() {
        notifier.update(5, 0)
        assertEquals(0, notifier.update(0, 5))
        assertNull(posted())
    }

    @Test
    fun `a fall lowers the baseline so the next rise notifies`() {
        assertEquals(2, notifier.update(2, 5))
        assertNull(posted())
    }

    @Test
    fun `text names no person batch or amount`() {
        notifier.update(4, 0)
        val text = posted()!!.extras.getCharSequence("android.text").toString()
        assertEquals(context.getString(com.shikkhokplus.app.R.string.tray_updates, 4), text)
        assertFalse(text.contains("Batch", ignoreCase = true))
        assertTrue(text.contains("4"))
    }

    @Test
    fun `without the permission nothing is posted but the baseline still advances`() {
        shadowOf(context).denyPermissions("android.permission.POST_NOTIFICATIONS")
        assertEquals(3, notifier.update(3, 0))
        assertNull(posted())
    }

    private fun tap() =
        android.content.Intent().putExtra(UnreadNotifier.EXTRA_OPEN, UnreadNotifier.OPEN_INBOX)

    @Test
    fun `a fresh launch from a tap opens the inbox`() {
        assertTrue(UnreadNotifier.opensInboxOnCreate(tap(), null))
    }

    @Test
    fun `a recreated activity never reopens the inbox`() {
        assertFalse(UnreadNotifier.opensInboxOnCreate(tap(), android.os.Bundle()))
    }

    @Test
    fun `a consumed tap cannot open the inbox again`() {
        val intent = tap()
        UnreadNotifier.consume(intent)
        assertFalse(UnreadNotifier.wantsInbox(intent))
        assertFalse(UnreadNotifier.opensInboxOnCreate(intent, null))
    }
}
