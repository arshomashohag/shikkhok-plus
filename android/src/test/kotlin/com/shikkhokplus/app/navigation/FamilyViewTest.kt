package com.shikkhokplus.app.navigation

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import com.shikkhokplus.app.core.network.FamilyBatchViewDto
import com.shikkhokplus.app.core.network.FamilyExamDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import com.shikkhokplus.app.core.network.StudentBatchDto
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.student.FamilyReader
import com.shikkhokplus.app.feature.student.StudentRepository
import com.shikkhokplus.app.feature.student.ui.NoticeDetailScreen
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import com.shikkhokplus.app.core.network.AnnouncementDto

/** A detail built first, with no batch screen having made the model. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class FamilyViewTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private class Repository : StudentRepository {
        override suspend fun batches() = AuthResult.Ok(listOf(StudentBatchDto("e-1", "Physics A")))

        override suspend fun phone(): AuthResult<MeDto> = AuthResult.TransportFailure

        override suspend fun batchView(enrollmentId: String) =
            AuthResult.Ok(
                FamilyBatchViewDto(
                    servedAt = "2026-10-28T09:00:00Z",
                    announcements = listOf(AnnouncementDto("a-1", "Bring a ruler", "2026-10-26T09:00:00Z")),
                ),
            )

        override suspend fun progress(enrollmentId: String) =
            AuthResult.Ok<List<ProgressEntryDto>>(emptyList())


        override suspend fun exam(enrollmentId: String, examId: String): AuthResult<FamilyExamDto> =
            AuthResult.TransportFailure
    }

    @Test
    fun `a notice detail renders from a fresh store, loading the seat itself`() {
        val owner = object : ViewModelStoreOwner {
            override val viewModelStore: ViewModelStore = ViewModelStore()
        }
        compose.setContent {
            val view = familyViewOf(owner, FamilyReader.SELF, "e-1") { Repository() }
            NoticeDetailScreen(view?.notice("a-1"), onBack = {})
        }

        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText("Bring a ruler").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("Bring a ruler").assertExists()
    }
}
