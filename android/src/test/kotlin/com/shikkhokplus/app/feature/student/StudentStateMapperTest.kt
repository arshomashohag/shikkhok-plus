package com.shikkhokplus.app.feature.student

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.AnnouncementDto
import com.shikkhokplus.app.core.network.AttendanceEntryDto
import com.shikkhokplus.app.core.network.CurrentFeeDto
import com.shikkhokplus.app.core.network.FamilyBatchViewDto
import com.shikkhokplus.app.core.network.ProgressEntryDto
import com.shikkhokplus.app.core.network.ScheduleSlotDto
import com.shikkhokplus.app.core.network.StudentBatchDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

/**
 * S1 and S2's mapping. The decisions are the server's; these pin that
 * the mapper names them and decides nothing itself.
 */
class StudentStateMapperTest {

    private fun seat(status: String? = "paid") =
        StudentBatchDto(
            enrollmentId = "e-1",
            batchName = "Physics A",
            teacherDisplayName = "Mahfuz",
            schedule = listOf(ScheduleSlotDto(5, "16:00:00", "17:30:00")),
            currentFee = status?.let { CurrentFeeDto("2026-10", it, "2026-10-10", Money.of("0.00")) },
        )

    private fun view(past: List<AttendanceEntryDto> = emptyList()) =
        FamilyBatchViewDto(
            nextSessionDate = "2026-10-31",
            nextSessionStartTime = "16:00:00",
            pastSessions = past,
            announcements = listOf(AnnouncementDto("a-1", "Bring a calculator", "2026-10-26T09:00:00Z")),
            servedAt = "2026-10-28T09:00:00Z",
        )

    @Test
    fun `no batches is the empty state carrying the student's number`() {
        val state = StudentStateMapper.afterBatches(emptyList(), "+8801611477203")

        assertEquals(MyBatchesUiState.Empty("+8801611477203"), state)
    }

    @Test
    fun `the fee status is the server's, named by its key`() {
        val state = StudentStateMapper.afterBatches(listOf(seat("partly_paid")), null)
        val loaded = assertIs<MyBatchesUiState.Loaded>(state)

        assertEquals("fees.status.partly_paid", loaded.rows.single().fee?.statusKey)
    }

    @Test
    fun `a seat before its first fee period shows no fee line`() {
        val loaded = assertIs<MyBatchesUiState.Loaded>(StudentBatchesOf(seat(status = null)))

        assertNull(loaded.rows.single().fee)
    }

    @Test
    fun `a fee status outside the four is a failure, not a guess`() {
        assertIs<MyBatchesUiState.Failed>(StudentStateMapper.afterBatches(listOf(seat("overdue")), null))
    }

    @Test
    fun `topics show only classes whose topic was logged with text`() {
        // `topicLogged` is the server's. A topic saved blank is logged
        // and has nothing to show; one never logged is not a topic.
        val past =
            listOf(
                AttendanceEntryDto("s-3", "2026-10-14", "16:00:00", true, "Thermodynamics", topicLogged = true),
                AttendanceEntryDto("s-2", "2026-10-12", "16:00:00", true, "", topicLogged = true),
                AttendanceEntryDto("s-1", "2026-10-10", "16:00:00", null, null, topicLogged = false),
            )

        val state = StudentStateMapper.afterBatch(seat(), view(past), emptyList())
        val loaded = assertIs<StudentBatchUiState.Loaded>(state)

        assertEquals(listOf(TopicRow("2026-10-14", "Thermodynamics")), loaded.view.topics)
    }

    @Test
    fun `the next class carries its start as HH-MM and the notices as sent`() {
        val loaded = assertIs<StudentBatchUiState.Loaded>(StudentStateMapper.afterBatch(seat(), view(), emptyList()))

        assertEquals("2026-10-31", loaded.view.nextClassDate)
        assertEquals("16:00", loaded.view.nextClassStart)
        assertEquals("Bring a calculator", loaded.view.notices.single().body)
    }

    @Test
    fun `an absent result keeps no mark, and an unknown state fails`() {
        val absent = ProgressEntryDto("x-1", "Weekly 3", "2026-10-05", 50, "absent", null)
        val loaded = assertIs<StudentBatchUiState.Loaded>(StudentStateMapper.afterBatch(seat(), view(), listOf(absent)))
        assertNull(loaded.view.results.single().marks)

        val unknown = absent.copy(resultState = "excused")
        assertIs<StudentBatchUiState.Failed>(StudentStateMapper.afterBatch(seat(), view(), listOf(unknown)))
    }

    /**
     * Map one seat as S1 would.
     *
     * @param dto The seat
     * @return The state
     */
    @Suppress("TestFunctionName")
    private fun StudentBatchesOf(dto: StudentBatchDto) = StudentStateMapper.afterBatches(listOf(dto), null)
}
