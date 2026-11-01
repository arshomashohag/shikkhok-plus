package com.shikkhokplus.app.core.notify

/**
 * Whether the app is on screen.
 *
 * The background unread check stands down while this is true: the open
 * app already shows the count and renews its own session, and two
 * clients renewing at once is how a refresh token gets reused.
 */
object AppForeground {
    @Volatile
    var visible: Boolean = false
}
