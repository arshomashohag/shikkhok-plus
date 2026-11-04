package com.shikkhokplus.app.core.designsystem

import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics

/**
 * Mark this text as a heading for TalkBack.
 *
 * **What it buys.** TalkBack's heading navigation lets a person swipe
 * from "Classes today" straight to "To verify" instead of through
 * every row in between. Without it, a screen-reader user on Today has
 * to hear each class before reaching the payments waiting for them.
 * It changes nothing visible.
 *
 * Applied to the top bar's title on every screen and to the section
 * headings, so there is one place to look for what counts as a heading.
 *
 * @return This modifier, carrying the heading role
 */
fun Modifier.asHeading(): Modifier = semantics { heading() }
