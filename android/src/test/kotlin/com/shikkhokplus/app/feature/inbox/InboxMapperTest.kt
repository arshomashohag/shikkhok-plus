package com.shikkhokplus.app.feature.inbox

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ExamBlockDto
import com.shikkhokplus.app.core.network.InboxDto
import com.shikkhokplus.app.core.network.NotificationDetailDto
import com.shikkhokplus.app.core.network.NotificationDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

/** The inbox's mapping and its tap targets. */
class InboxMapperTest {

    private fun dto(
        kind: String,
        child: String? = null,
        enrollment: String? = "e-1",
        source: String? = "x-1",
    ) = NotificationDto(
        notificationId = "n-1",
        kind = kind,
        enrollmentId = enrollment,
        batchName = "Physics",
        createdAt = "2026-10-17T06:00:00Z",
        read = false,
        sourceId = source,
        childName = child,
        preview = "Bring a calculator",
    )

    private fun messages(vararg items: NotificationDto) =
        assertIs<InboxUiState.Loaded>(InboxMapper.afterLoad(InboxDto(items.toList(), items.size))).messages

    @Test
    fun `an unknown kind is dropped and every known kind is kept`() {
        val known =
            listOf(
                "fee_reminder", "payment_approved", "payment_partial", "payment_rejected",
                "payment_recorded", "notice", "exam_scheduled", "exam_cancelled",
                "marks_available", "claim_to_verify",
            )
        val kept = messages(*(known + "future").map { dto(it) }.toTypedArray())

        assertEquals(10, kept.size)
        assertEquals(InboxKind.entries.toSet(), kept.map { it.kind }.toSet())
    }

    @Test
    fun `the child's name and the preview are kept`() {
        val message = messages(dto("notice", child = "Rahim")).single()

        assertEquals("Rahim", message.childName)
        assertEquals("Bring a calculator", message.preview)
    }

    @Test
    fun `notices, exams and payment results open their detail`() {
        listOf(
            "notice", "exam_scheduled", "exam_cancelled", "payment_approved", "payment_partial",
            "payment_rejected", "payment_recorded",
        ).forEach {
            assertEquals(InboxTarget.Detail("n-1"), InboxMapper.targetOf(messages(dto(it)).single()), it)
        }
    }

    @Test
    fun `marks open the marksheet as the child's guardian or as oneself`() {
        assertEquals(
            InboxTarget.Marksheet("x-1", "e-1", guardian = true),
            InboxMapper.targetOf(messages(dto("marks_available", child = "Rahim")).single()),
        )
        assertEquals(
            InboxTarget.Marksheet("x-1", "e-1", guardian = false),
            InboxMapper.targetOf(messages(dto("marks_available")).single()),
        )
    }

    @Test
    fun `a fee reminder opens the fee history and a claim opens its payment`() {
        // Shaped as the server sends a reminder: no source, no preview, a
        // period and an amount, and the child's name on a guardian's copy
        // only. The name is what routes it to the child's fee read.
        fun reminder(child: String?) =
            dto("fee_reminder", child = child, source = null)
                .copy(period = "2026-10", amount = Money.of("1200.00"), preview = null)

        assertEquals(
            InboxTarget.Fees("e-1", guardian = true),
            InboxMapper.targetOf(messages(reminder("Rahim")).single()),
        )
        assertEquals(
            InboxTarget.Fees("e-1", guardian = false),
            InboxMapper.targetOf(messages(reminder(null)).single()),
        )
        assertEquals(
            InboxTarget.Payment("x-1"),
            InboxMapper.targetOf(messages(dto("claim_to_verify")).single()),
        )
        assertEquals(
            InboxTarget.Verify,
            InboxMapper.targetOf(messages(dto("claim_to_verify", source = null)).single()),
        )
    }

    @Test
    fun `an item missing what its screen needs falls back to its detail`() {
        assertEquals(
            InboxTarget.Detail("n-1"),
            InboxMapper.targetOf(messages(dto("marks_available", source = null)).single()),
        )
        assertEquals(
            InboxTarget.Detail("n-1"),
            InboxMapper.targetOf(messages(dto("fee_reminder", enrollment = null)).single()),
        )
    }

    @Test
    fun `a cancelled exam opens to the exam, marked cancelled`() {
        val exam =
            ExamBlockDto(
                examId = "x-1",
                title = "Monthly",
                date = "2026-11-20",
                subjectName = "Physics",
                totalMarks = 50,
                cancelled = true,
            )
        val opened =
            InboxMapper.afterDetail(
                NotificationDetailDto(
                    notificationId = "n-1",
                    kind = "exam_cancelled",
                    batchName = "Physics",
                    createdAt = "2026-11-05T06:00:00Z",
                    read = false,
                    preview = "Monthly · 2026-11-20",
                    exam = exam,
                ),
            )

        val loaded = assertIs<InboxDetailUiState.Loaded>(opened)
        assertEquals(InboxKind.EXAM_CANCELLED, loaded.detail.kind)
        val content = assertIs<InboxContent.Exam>(loaded.detail.content)
        assertEquals(true, content.cancelled)
    }

    @Test
    fun `an exam block from a server older than cancelling reads as not cancelled`() {
        val exam =
            ExamBlockDto(examId = "x-1", title = "Monthly", date = "2026-11-20", subjectName = "P", totalMarks = 5)

        assertEquals(false, exam.cancelled)
    }
}
