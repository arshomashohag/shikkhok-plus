package com.shikkhokplus.app.feature.hubreviews

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import com.shikkhokplus.app.core.designsystem.ShikkhokTheme
import com.shikkhokplus.app.feature.hubreviews.ui.OwnerReviewsActions
import com.shikkhokplus.app.feature.hubreviews.ui.OwnerReviewsScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertTrue

/**
 * The owner's Reviews screen in Bangla keeps its figures in Latin digits.
 *
 * **Found in review.** The count, the distribution and the stars' label
 * passed a raw `Int` to a `%d` placeholder, which a Bangla locale formats
 * in Bengali digits -- the numeral rule says Latin, as the web and the
 * public pages show them. The figures now go through `Numerals.count`.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "bn-rBD-w400dp-h1600dp")
class OwnerReviewsScreenBanglaTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun `under Bangla every figure is in Latin digits`() {
        val content =
            OwnerReviewsContent(
                batches =
                    listOf(
                        OwnerBatchRating(
                            batchId = "b-1",
                            batchTitle = "পদার্থবিজ্ঞান ৯",
                            reviewCount = 3,
                            averageLabel = "4.3",
                            distribution = listOf(0, 0, 0, 2, 1),
                        ),
                    ),
                cards = listOf(ReplyCard(ownerReview())),
            )

        compose.setContent {
            ShikkhokTheme { OwnerReviewsScreen(OwnerReviewsUiState.Ready(content), OwnerReviewsActions()) }
        }

        compose.onNodeWithText("3টি রিভিউ").assertExists()
        compose.onNodeWithText("5★ · 1").assertExists()
        compose.onNodeWithText("4★ · 2").assertExists()
        compose.onNodeWithText("4.3", substring = true).assertExists()
        assertTrue(
            compose.onAllNodesWithContentDescription("5-এর মধ্যে 5 তারকা").fetchSemanticsNodes().isNotEmpty(),
            "the stars are read aloud with a Latin 5",
        )
        // Nothing on the screen carries a Bengali digit but the batch's own title.
        val bengali = Regex("[০-৯]")
        listOf("৩টি", "৫★", "৪★", "৫-এর মধ্যে ৫").forEach { text ->
            assertTrue(
                compose.onAllNodesWithText(text, substring = true).fetchSemanticsNodes().isEmpty() &&
                    compose.onAllNodesWithContentDescription(text, substring = true).fetchSemanticsNodes().isEmpty(),
                "found Bengali digits: $text",
            )
        }
        assertTrue(bengali.containsMatchIn("পদার্থবিজ্ঞান ৯"), "the fixture's title is the only Bengali-digit text")
    }
}
