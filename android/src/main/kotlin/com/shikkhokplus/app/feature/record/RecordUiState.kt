package com.shikkhokplus.app.feature.record

import com.shikkhokplus.app.core.network.SubjectOptionDto

/**
 * The class being recorded, as the screen that opened the sheet knows it.
 *
 * @property sessionId The class
 * @property batchId Its batch
 * @property title What the sheet's subtitle names, e.g. `Physics · Batch A`
 * @property startTime `HH:MM`
 * @property topicVersion The version the topic write composes against
 * @property subjectName The subject already set, if any
 */
data class RecordTarget(
    val sessionId: String,
    val batchId: String,
    val title: String,
    val startTime: String,
    val topicVersion: Int,
    val subjectName: String?,
)

/** How saving went. */
enum class SaveResult {
    /** The server has the topic. */
    SENT,

    /** Kept on the phone; the queue sends it when the connection returns. */
    QUEUED,

    /** Someone saved a different topic first; nothing was overwritten. */
    CONFLICTED,
}

/**
 * The open "Record class" sheet.
 *
 * @property target The class
 * @property subjects The batch's subjects; one or none means no picker
 * @property subjectId The chosen subject
 * @property typed The topic as typed
 * @property suggestion The last topic logged in this batch, to continue
 * @property saving A save is in flight
 * @property errorKey A refused subject change, shown in the sheet
 */
data class RecordSheet(
    val target: RecordTarget,
    val subjects: List<SubjectOptionDto> = emptyList(),
    val subjectId: String? = null,
    val typed: String = "",
    val suggestion: String? = null,
    val saving: Boolean = false,
    val errorKey: String? = null,
)
