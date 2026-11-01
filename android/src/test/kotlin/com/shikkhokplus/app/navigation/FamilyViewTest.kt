package com.shikkhokplus.app.navigation

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import com.shikkhokplus.app.core.network.FamilyBatchViewDto
import com.shikkhokplus.app.core.network.FamilyExamDto
import com.shikkhokplus.app.core.format.YearMonth
import com.shikkhokplus.app.core.network.CalendarClassDto
import com.shikkhokplus.app.core.network.CalendarDayDto
import com.shikkhokplus.app.core.network.MeDto
import com.shikkhokplus.app.core.network.MonthViewDto
import com.shikkhokplus.app.feature.student.ui.ClassDetailScreen
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
import kotlin.test.assertEquals
import com.shikkhokplus.app.core.network.AnnouncementDto

/** A detail built first, with no batch screen having made the model. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class FamilyViewTest {

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private class Repository : StudentRepository {
        val months = mutableListOf<YearMonth>()

        override suspend fun month(enrollmentId: String, year: Int, month: Int): AuthResult<MonthViewDto> {
            months += YearMonth(year, month)
            return AuthResult.Ok(
                MonthViewDto(
                    year, month, "2026-01", "2026-12",
                    days =
                        listOf(
                            CalendarDayDto(
                                "2026-10-14", "taken",
                                listOf(
                                    CalendarClassDto(
                                        "s-1",
                                        "2026-10-14",
                                        "16:00:00",
                                        state = "taken",
                                        topic = "Optics",
                                    ),
                                ),
                            ),
                        ),
                ),
            )
        }

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

    @Test
    fun `a class detail renders from a fresh store, loading the month it was opened on`() {
        val owner = object : ViewModelStoreOwner {
            override val viewModelStore: ViewModelStore = ViewModelStore()
        }
        val repository = Repository()
        compose.setContent {
            val (clazz, loading) =
                familyClassOf(owner, FamilyReader.SELF, "e-1", YearMonth(2026, 10), "s-1") { repository }
            ClassDetailScreen(clazz, onBack = {}, loading = loading)
        }

        compose.waitUntil(timeoutMillis = 5_000) {
            compose.onAllNodesWithText("Optics").fetchSemanticsNodes().isNotEmpty()
        }
        assertEquals(listOf(YearMonth(2026, 10)), repository.months)
    }
}
