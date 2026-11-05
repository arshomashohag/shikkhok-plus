package com.shikkhokplus.app.feature.dashboard.ui

import com.shikkhokplus.app.core.network.DashboardExamDto

/**
 * The three lines of the marks chart, as fractions of each exam's total.
 *
 * Each entry is a server integer over the exam's own total, a drawing
 * coordinate and not a figure to show. A null is a gap: an absence is
 * never drawn as a zero.
 *
 * @property own The seat's marks
 * @property average The batch average
 * @property highest The batch highest
 */
data class MarksSeries(
    val own: List<Float?>,
    val average: List<Float?>,
    val highest: List<Float?>,
) {
    /** Whether any exam carries a batch average. */
    val hasAverage: Boolean get() = average.any { it != null }

    /** Whether any exam carries a batch highest. */
    val hasHighest: Boolean get() = highest.any { it != null }
}

/**
 * Turn the server's exams into chart positions.
 *
 * @param exams The exams, oldest first
 * @return The three series
 */
fun marksSeries(exams: List<DashboardExamDto>): MarksSeries =
    MarksSeries(
        own = exams.map { fraction(it.marks, it.total) },
        average = exams.map { fraction(it.batchAverage, it.total) },
        highest = exams.map { fraction(it.batchHighest, it.total) },
    )

private fun fraction(
    value: Double?,
    total: Int,
): Float? = if (value == null || total <= 0) null else (value / total).toFloat().coerceIn(0f, 1f)
