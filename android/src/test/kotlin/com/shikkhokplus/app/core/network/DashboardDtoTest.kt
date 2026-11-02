package com.shikkhokplus.app.core.network

import com.shikkhokplus.app.core.model.Money
import kotlinx.serialization.SerializationException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

/** The dashboard response, decoded with the app's real JSON. */
class DashboardDtoTest {
    private fun body(owed: String) =
        """{"tiles":{"attendance_percent":86,"present":43,"held":50,"exam_average_percent":null,
           "direction":null,"owed":$owed},
           "attendance_by_month":[{"period":"2026-10","held":4,"present":3,"percent":75,"in_progress":true}],
           "exams":[{"exam_id":"x","title":"Ch-5","date":"2026-10-22","subject":null,"marks":81,"total":100,
           "percent":81,"batch_average":null,"batch_highest":null}],
           "fee_months":[{"period":"2026-10","state":"partly_paid"}]}"""

    @Test
    fun `owed decodes from a string and keeps nulls`() {
        val dto = ApiClient.json.decodeFromString(DashboardDto.serializer(), body("\"2000.00\""))

        assertEquals(Money.of("2000.00"), dto.tiles.owed)
        assertNull(dto.tiles.examAveragePercent)
        assertNull(dto.exams.single().batchAverage)
        assertEquals("partly_paid", dto.feeMonths.single().state)
        assertEquals(true, dto.attendanceByMonth.single().inProgress)
    }

    @Test
    fun `owed REFUSES a JSON number`() {
        assertFailsWith<SerializationException> {
            ApiClient.json.decodeFromString(DashboardDto.serializer(), body("2000.00"))
        }
    }
}
