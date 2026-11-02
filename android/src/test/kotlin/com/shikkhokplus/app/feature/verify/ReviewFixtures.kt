package com.shikkhokplus.app.feature.verify

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.PaymentReviewDto
import com.shikkhokplus.app.core.network.ReviewChildDto
import com.shikkhokplus.app.core.network.ReviewMethodDto

/** A child on a payment, owing the amount given. */
fun reviewChild(
    id: String,
    name: String,
    owed: String = "1000.00",
) = ReviewChildDto(
    enrollmentId = id,
    claimId = "claim-$id",
    displayName = name,
    period = "2026-10",
    owed = Money.of(owed),
)

/** A payment under review, with the figures the server would state. */
fun review(
    comparison: String = "matches",
    total: String = "2000.00",
    owedTogether: String = "2000.00",
    difference: String = "0.00",
    status: String = "pending",
    decisionNote: String? = null,
    children: List<ReviewChildDto> = listOf(reviewChild("e-1", "Rafsan"), reviewChild("e-2", "Tasnim")),
) = PaymentReviewDto(
    submissionId = "s-1",
    batchName = "Physics A",
    children = children,
    owedTogether = Money.of(owedTogether),
    totalAmount = Money.of(total),
    comparison = comparison,
    difference = Money.of(difference),
    method = ReviewMethodDto(kind = "mobile", provider = "bKash", mobileNumber = "01711234567"),
    transactionId = "BJK40OQ1IL",
    paidOn = "2026-10-28",
    submittedAt = "2026-10-28T10:00:00Z",
    submittedBy = "guardian",
    submitterPhone = "+8801711234567",
    status = status,
    decisionNote = decisionNote,
)
