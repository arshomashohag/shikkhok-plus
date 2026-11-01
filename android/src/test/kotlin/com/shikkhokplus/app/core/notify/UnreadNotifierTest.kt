package com.shikkhokplus.app.core.notify

import android.app.Application
import android.app.NotificationManager
import android.content.Context
import androidx.test.core.app.ApplicationProvider
import com.shikkhokplus.app.R
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
 * The tray notification posts for a new item and says nothing otherwise.
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
        assertEquals("n-3", notifier.update(3, "n-3", null))
        assertEquals(3, posted()!!.number)
    }

    @Test
    fun `the same newest item posts nothing again`() {
        assertEquals("n-3", notifier.update(3, "n-3", "n-3"))
        assertNull(posted())
    }

    @Test
    fun `a new newest item updates to the new count`() {
        notifier.update(3, "n-3", null)
        assertEquals("n-5", notifier.update(5, "n-5", "n-3"))
        assertEquals(5, posted()!!.number)
    }

    @Test
    fun `one new item after reading three in the app still posts`() {
        // Told about three, all read in the app, then one more arrives.
        // A count baseline of 3 would stay silent on a count of 1; the
        // newest unread item is new, so the person is told.
        notifier.update(3, "n-3", null)
        notifier.cancel()

        assertEquals("n-4", notifier.update(1, "n-4", "n-3"))
        assertEquals(1, posted()!!.number)
    }

    @Test
    fun `reading everything cancels the notification and forgets the item`() {
        notifier.update(5, "n-5", null)
        assertNull(notifier.update(0, null, "n-5"))
        assertNull(posted())
    }

    @Test
    fun `fewer unread with the same newest item posts nothing`() {
        assertEquals("n-5", notifier.update(2, "n-5", "n-5"))
        assertNull(posted())
    }

    @Test
    fun `text names no person batch or amount, in the right plural`() {
        notifier.update(4, "n-4", null)
        val text = posted()!!.extras.getCharSequence("android.text").toString()
        assertEquals(context.resources.getQuantityString(R.plurals.tray_updates, 4, 4), text)
        assertEquals("4 new updates", text)
        assertFalse(text.contains("Batch", ignoreCase = true))

        notifier.update(1, "n-5", "n-4")
        assertEquals("1 new update", posted()!!.extras.getCharSequence("android.text").toString())
    }

    @Test
    fun `without the permission nothing is posted but the item is still remembered`() {
        shadowOf(context).denyPermissions("android.permission.POST_NOTIFICATIONS")
        assertEquals("n-3", notifier.update(3, "n-3", null))
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
