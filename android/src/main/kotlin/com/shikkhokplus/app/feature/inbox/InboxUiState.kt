package com.shikkhokplus.app.feature.inbox

import com.shikkhokplus.app.core.model.Money

/** What a message is about, as the server named it. */
enum class InboxKind {
    /** A teacher's reminder that a fee is owed. */
    FEE_REMINDER,

    /** A payment the teacher approved. */
    PAYMENT_APPROVED,

    /** A payment the teacher accepted in part. */
    PAYMENT_PARTIAL,

    /** A payment the teacher did not accept. */
    PAYMENT_REJECTED,

    /** Money the teacher received by hand and recorded themselves. */
    PAYMENT_RECORDED,

    /** A notice a teacher posted. */
    NOTICE,

    /** An exam a teacher scheduled. */
    EXAM_SCHEDULED,

    /** An exam a teacher cancelled before its results were out. */
    EXAM_CANCELLED,

    /** Marks a teacher released. */
    MARKS_AVAILABLE,

    /** A payment waiting for the teacher to check. */
    CLAIM_TO_VERIFY,

    /** A class the teacher cancelled before it was held. */
    CLASS_CANCELLED,

    /** A class the teacher moved to another day or time. */
    CLASS_RESCHEDULED,

    /** An administrator suspended the owner's public listing. */
    HUB_LISTING_SUSPENDED,

    /** "Did the hub bring you a student?", asked 60 and 90 days after the first publish. */
    HUB_FEEDBACK_QUESTION,
}

/**
 * Which class a class-change message names, as the server sent it.
 *
 * @property date The day the class is on now, or was on if cancelled, as `YYYY-MM-DD`
 * @property time Its start time, as `HH:MM:SS`
 * @property movedFromDate For a move, the day it was on before
 * @property movedFromTime For a move, the start time before
 */
data class ClassChange(
    val date: String,
    val time: String,
    val movedFromDate: String? = null,
    val movedFromTime: String? = null,
)

/**
 * One message, as the inbox shows it.
 *
 * @property id The message
 * @property batchName The batch it is about
 * @property amount What is owed, as the server computed it, if any
 * @property period The period the debt starts in, if any
 * @property sentAt When it was sent
 * @property unread Whether it arrived since the inbox was last opened
 * @property kind What it is about
 * @property enrollmentId The seat it is about, if any
 * @property sourceId The record that produced it, if any
 * @property childName Which child it is about, on a guardian's copy
 * @property preview A short line of its content, if any
 * @property classChange The class it names, for a class change
 * @property feedbackDay For the hub's demand question, which one: 60 or 90
 */
data class InboxMessage(
    val id: String,
    val batchName: String,
    val amount: Money?,
    val period: String?,
    val sentAt: String,
    val unread: Boolean,
    val kind: InboxKind = InboxKind.FEE_REMINDER,
    val enrollmentId: String? = null,
    val sourceId: String? = null,
    val childName: String? = null,
    val preview: String? = null,
    val classChange: ClassChange? = null,
    val feedbackDay: Int? = null,
)

/** Where tapping an item leads, decided from the server's fields. */
sealed interface InboxTarget {
    /**
     * The item's own detail screen.
     *
     * @property id The message
     */
    data class Detail(val id: String) : InboxTarget

    /**
     * A marksheet.
     *
     * @property examId The exam
     * @property enrollmentId The seat
     * @property guardian True on a guardian's copy
     */
    data class Marksheet(val examId: String, val enrollmentId: String, val guardian: Boolean) : InboxTarget

    /**
     * A seat's fee history.
     *
     * @property enrollmentId The seat
     * @property guardian True on a guardian's copy
     */
    data class Fees(val enrollmentId: String, val guardian: Boolean) : InboxTarget

    /** The teacher's payments to check. */
    data object Verify : InboxTarget

    /** The owner's public listing, to read why it was suspended. */
    data object HubListing : InboxTarget

    /**
     * The hub's demand question, to answer it.
     *
     * @property ownerId The listing's owner, sent back as the workspace
     * @property day Which question: 60 or 90
     */
    data class HubFeedback(val ownerId: String, val day: Int) : InboxTarget

    /**
     * One payment to check, opened at its review.
     *
     * @property submissionId The payment
     */
    data class Payment(val submissionId: String) : InboxTarget
}

/** Everything the inbox screen and the bell render. */
sealed interface InboxUiState {
    /** A request is in flight. */
    data object Loading : InboxUiState

    /**
     * Read.
     *
     * @property messages Newest first, as the server ordered them
     * @property unread The badge's number, counted by the server
     */
    data class Loaded(val messages: List<InboxMessage>, val unread: Int) : InboxUiState

    /**
     * It failed.
     *
     * @property messageKey Names a string resource
     * @property retryable Read from the server's envelope
     */
    data class Failed(val messageKey: String, val retryable: Boolean) : InboxUiState
}
