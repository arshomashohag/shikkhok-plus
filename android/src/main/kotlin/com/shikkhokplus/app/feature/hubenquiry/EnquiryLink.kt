package com.shikkhokplus.app.feature.hubenquiry

import android.net.Uri
import com.shikkhokplus.app.feature.hublisting.report.UUID_TEXT

/**
 * Who a link asks: an owner by its public slug, and optionally one of its
 * batches by id.
 *
 * @property owner The owner's slug, as the link carried it
 * @property batch The batch's id, or null for the owner as a whole
 */
data class EnquiryRecipient(val owner: String, val batch: String?)

/**
 * An "Ask to join" link as it arrived: the two query values, unchecked, so
 * that a malformed link still opens the form and is refused there, in
 * words. The twin of `ReportLink`, with the same host and scheme checks.
 *
 * @property owner The `owner` query value, if any
 * @property batch The `batch` query value, if any
 */
data class EnquiryLink(val owner: String?, val batch: String?) {
    /**
     * Who the link asks, or null when it is not one the form takes: no
     * owner, or a batch that is not a UUID. The slug itself is the
     * server's to judge; it answers one not-found for every slug it will
     * not take requests for.
     */
    val recipient: EnquiryRecipient?
        get() {
            val slug = owner?.takeIf { it.isNotBlank() } ?: return null
            if (batch != null && !UUID_TEXT.matches(batch)) return null
            return EnquiryRecipient(slug, batch)
        }

    companion object {
        /** The path a public page's "Ask to join" link opens, on the web-app host. */
        const val PATH: String = "/ui/hub-enquiry"

        /**
         * Read an incoming link. Only `https://<host>/ui/hub-enquiry` is an
         * enquiry link: the manifest claims no other, and anything else
         * arriving here is ignored.
         *
         * @param uri The intent's data, if any
         * @param host The app-link host this build claims
         * @return The link's query values, or null when it is not an enquiry link
         */
        fun from(uri: Uri?, host: String): EnquiryLink? =
            uri?.takeIf { it.scheme == "https" && it.host == host && it.path == PATH }
                ?.let { EnquiryLink(it.getQueryParameter("owner"), it.getQueryParameter("batch")) }
    }
}
