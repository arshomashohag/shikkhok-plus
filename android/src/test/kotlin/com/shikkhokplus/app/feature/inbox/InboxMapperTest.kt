package com.shikkhokplus.app.feature.inbox

import com.shikkhokplus.app.core.network.InboxDto
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
                "notice", "exam_scheduled", "marks_available", "claim_to_verify",
            )
        val kept = messages(*(known + "future").map { dto(it) }.toTypedArray())

        assertEquals(8, kept.size)
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
        listOf("notice", "exam_scheduled", "payment_approved", "payment_partial", "payment_rejected").forEach {
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
    fun `a fee reminder opens the fee history and a claim opens the queue`() {
        assertEquals(
            InboxTarget.Fees("e-1", guardian = true),
            InboxMapper.targetOf(messages(dto("fee_reminder", child = "Rahim")).single()),
        )
        assertEquals(InboxTarget.Verify, InboxMapper.targetOf(messages(dto("claim_to_verify")).single()))
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
}
