package com.shikkhokplus.app.feature.hubreviews.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import com.shikkhokplus.app.R
import com.shikkhokplus.app.core.designsystem.Banner
import com.shikkhokplus.app.core.designsystem.BannerTone
import com.shikkhokplus.app.core.designsystem.TextAction
import com.shikkhokplus.app.core.format.Numerals
import com.shikkhokplus.app.core.format.dayMonthYear
import com.shikkhokplus.app.feature.auth.MessageKeys
import com.shikkhokplus.app.feature.hubreviews.RATING_MAX
import com.shikkhokplus.app.feature.hubreviews.ReviewFailure
import com.shikkhokplus.app.feature.hubreviews.ReviewReason
import com.shikkhokplus.app.feature.hubreviews.ReviewStatusWords
import com.shikkhokplus.app.feature.hubreviews.Tenure
import com.shikkhokplus.app.feature.hubreviews.statusWords

/**
 * A status in its author's words: "Awaiting review", "Published", "Not
 * published: it shows personal information". Held reads as awaiting.
 *
 * @param status The server's status
 * @param code The rejection code, for a rejected or removed one
 * @return The words, or null for a status this version does not know
 */
@Composable
internal fun statusText(status: String, code: String?): String? =
    when (statusWords(status)) {
        ReviewStatusWords.AWAITING -> stringResource(R.string.hub_review_status_pending)
        ReviewStatusWords.APPROVED -> stringResource(R.string.hub_review_status_approved)
        ReviewStatusWords.PUBLISHED -> stringResource(R.string.hub_review_status_published)
        ReviewStatusWords.NOT_PUBLISHED -> {
            val reason = stringResource(reasonText(ReviewReason.fromWire(code)))
            stringResource(R.string.hub_review_status_not_published, reason)
        }
        null -> null
    }

/**
 * The words for a reason.
 *
 * @param reason The reason
 * @return Its string resource
 */
private fun reasonText(reason: ReviewReason): Int =
    when (reason) {
        ReviewReason.IDENTIFIABLE_CHILD -> R.string.hub_review_reason_identifiable_child
        ReviewReason.PERSONAL_INFO -> R.string.hub_review_reason_personal_info
        ReviewReason.ABUSIVE -> R.string.hub_review_reason_abusive
        ReviewReason.OFF_TOPIC -> R.string.hub_review_reason_off_topic
        ReviewReason.OTHER -> R.string.hub_review_reason_other
    }

/**
 * Who wrote a review, as the public reads it: a tenure, never a name.
 *
 * @param wire The server's bucket
 * @return The label, or null for a bucket this version does not know
 */
@Composable
internal fun tenureText(wire: String): String? =
    when (Tenure.fromWire(wire)) {
        Tenure.LT_6M -> stringResource(R.string.hub_review_tenure_lt_6m)
        Tenure.M6_12 -> stringResource(R.string.hub_review_tenure_6_12m)
        Tenure.GT_1Y -> stringResource(R.string.hub_review_tenure_gt_1y)
        null -> null
    }

/**
 * A rating as stars, read aloud as "4 out of 5 stars".
 *
 * @param rating 1 to 5
 */
@Composable
internal fun RatingStars(rating: Int) {
    val label = stringResource(R.string.hub_review_stars, Numerals.count(rating))
    val shown = rating.coerceIn(0, RATING_MAX)
    Text(
        "★".repeat(shown) + "☆".repeat(RATING_MAX - shown),
        style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.semantics { contentDescription = label },
    )
}

/**
 * The words-count under a review or reply box.
 *
 * @param length How many characters are typed
 * @param max The server's limit
 * @return `12/1000`, in Latin digits
 */
@Composable
internal fun countText(length: Int, max: Int): String =
    stringResource(R.string.hub_report_note_count, Numerals.count(length), Numerals.count(max))

/**
 * A failed write: what failed, the server's words, the day it names, and
 * Retry when trying again can help.
 *
 * @param prefix What failed, such as "Your review was not saved."
 * @param failure The failure
 * @param onRetry Repeats it
 * @param retryTag The Retry control's tag
 */
@Composable
internal fun WriteFailed(prefix: String, failure: ReviewFailure, onRetry: () -> Unit, retryTag: String) {
    val day = failure.eligibleFrom?.let { stringResource(R.string.hub_review_eligible_from, dayMonthYear(it)) }
    Banner(
        title = prefix,
        body = listOfNotNull(stringResource(MessageKeys.resolve(failure.messageKey)), day).joinToString("\n"),
        tone = BannerTone.ERROR,
        action =
            if (failure.canRetry) {
                { TextAction(stringResource(R.string.auth_retry), onRetry, Modifier.testTag(retryTag)) }
            } else {
                null
            },
    )
}
