package com.shikkhokplus.app.feature.guardian

import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.shikkhokplus.app.feature.guardian.ui.MyChildrenScreen
import com.shikkhokplus.app.feature.guardian.ui.TAG_MY_CHILD_ROW
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.test.assertEquals

/**
 * My children (G4): a list to read, with what to do when a child is
 * missing. Choosing a child selects it on the home switcher [BR4.2].
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MyChildrenScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private fun child(name: String, batches: Int) =
        ChildCard(
            key = "seat-$name",
            name = name,
            batchCount = batches,
            payment = null,
            waiting = emptyList(),
            results = emptyList(),
            batches = emptyList(),
        )

    private val loaded = GuardianUiState.Loaded(children = listOf(child("Tasnim", 3), child("Ayan", 1)))

    @Test
    fun `every child is listed with their batch count`() {
        compose.setContent {
            MyChildrenScreen(state = loaded, phone = null, onBack = {}, onChild = {}, onRetry = {})
        }

        compose.onAllNodesWithTag(TAG_MY_CHILD_ROW).assertCountEquals(2)
        compose.onNodeWithText("3 batches").assertIsDisplayed()
        compose.onNodeWithText("1 batch").assertIsDisplayed()
    }

    @Test
    fun `tapping a child reports its position`() {
        var chosen: Int? = null
        compose.setContent {
            MyChildrenScreen(state = loaded, phone = null, onBack = {}, onChild = { chosen = it }, onRetry = {})
        }

        compose.onNodeWithText("Ayan").performClick()

        assertEquals(1, chosen)
    }

    @Test
    fun `a missing child is explained with the guardian's own number`() {
        compose.setContent {
            MyChildrenScreen(
                state = GuardianUiState.Empty(phone = null),
                phone = "+8801819552041",
                onBack = {},
                onChild = {},
                onRetry = {},
            )
        }

        compose.onNodeWithText("A child is missing?").assertIsDisplayed()
        compose.onNodeWithText("01819-552041", substring = true).assertIsDisplayed()
    }

    @Test
    fun `without a known number the note still says who to ask`() {
        compose.setContent {
            MyChildrenScreen(state = loaded, phone = null, onBack = {}, onChild = {}, onRetry = {})
        }

        compose.onNodeWithText("Ask the teacher to add your number as the guardian.").assertIsDisplayed()
    }
}
