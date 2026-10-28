package com.shikkhokplus.app.core.ui

import com.shikkhokplus.app.core.network.ScheduleSlotDto
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** The schedule draft: days plus one time range, into slots and back. */
class ScheduleDraftTest {

    @Test
    fun `slots come out in Bangladesh's week order, Saturday first`() {
        // Server numbering: 0 = Monday ... 5 = Saturday, 6 = Sunday.
        val draft = ScheduleDraft(days = setOf(2, 5, 0), start = "16:00", end = "17:30")

        assertEquals(listOf(5, 0, 2), draft.toSlots().map { it.weekday })
        assertTrue(draft.toSlots().all { it.startTime == "16:00" && it.endTime == "17:30" })
    }

    @Test
    fun `a class must end after it starts`() {
        assertFalse(ScheduleDraft(setOf(0), "17:00", "16:00").isValid)
        assertFalse(ScheduleDraft(setOf(0), "16:00", "16:00").isValid)
        assertTrue(ScheduleDraft(setOf(0), "16:00", "16:01").isValid)
    }

    @Test
    fun `no days is a valid, empty schedule`() {
        // Clearing a schedule is allowed; the times then do not matter.
        val draft = ScheduleDraft(emptySet(), "17:00", "16:00")
        assertTrue(draft.isValid)
        assertEquals(emptyList(), draft.toSlots())
    }

    @Test
    fun `a stored schedule reads back into the same draft`() {
        val stored = listOf(ScheduleSlotDto(0, "16:00", "17:30"), ScheduleSlotDto(2, "16:00", "17:30"))

        val draft = ScheduleDraft.of(stored)

        assertEquals(setOf(0, 2), draft.days)
        assertEquals(stored, draft.toSlots())
    }

    @Test
    fun `times show in the canvas's twelve-hour form, Latin digits`() {
        assertEquals("4:00 pm", displayTime("16:00"))
        assertEquals("12:30 pm", displayTime("12:30"))
        assertEquals("12:05 am", displayTime("00:05"))
        assertEquals("9:15 am", displayTime("09:15"))
    }
}
