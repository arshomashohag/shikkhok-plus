package com.shikkhokplus.app.feature.batchdetail

import com.shikkhokplus.app.core.model.Money
import com.shikkhokplus.app.core.network.ScheduleSlotDto
import com.shikkhokplus.app.core.ui.WriteState

/** The four tabs of a batch (T7). */
enum class BatchTab {
    /** The roster, with each student's fee chip. */
    STUDENTS,

    /** The batch's classes. */
    CLASSES,

    /** The batch's exams, grouped by where they stand. */
    EXAMS,

    /** Notices to students and guardians. */
    NOTICES,
}

/**
 * What the header says about a batch.
 *
 * @property name The batch
 * @property defaultFee The monthly fee, if set
 * @property feeDueDay The day of the month fees fall due, if set
 * @property schedule The weekly classes
 * @property subjects The subjects taught
 */
data class BatchHeader(
    val name: String,
    val defaultFee: Money?,
    val feeDueDay: Int?,
    val schedule: List<ScheduleSlotDto>,
    val subjects: List<String>,
)

/** Which kind of fee chip a student gets, as the server's fields decide. */
enum class FeeChipKind {
    /** A payment waits for the teacher to check. */
    VERIFYING,

    /** Owing past its due date, with how many days. */
    OVERDUE,

    /** Part of the current period paid. */
    PARTIAL,

    /** The current period paid. */
    PAID,

    /** The current period waived. */
    WAIVED,

    /** The current period owing and not yet late. */
    DUE,
}

/**
 * One student's fee chip.
 *
 * @property kind Which chip
 * @property amount The figure it shows, where it shows one
 * @property days Days overdue, for an overdue chip
 * @property dueDate The due date, `YYYY-MM-DD`, for a due chip
 */
data class FeeChip(
    val kind: FeeChipKind,
    val amount: Money? = null,
    val days: Int? = null,
    val dueDate: String? = null,
)

/**
 * The fee chips, or that they could not load.
 *
 * The design hides fee status rather than showing it out of date when
 * the read fails, so a failure is its own state rather than no chips.
 */
sealed interface FeeChips {
    /** Still loading. */
    data object Loading : FeeChips

    /**
     * Loaded.
     *
     * @property bySeat Each seat's chip, absent where nothing has generated
     */
    data class Loaded(val bySeat: Map<String, FeeChip>) : FeeChips

    /** Could not load; the chips are hidden. */
    data object Failed : FeeChips
}

/**
 * One notice.
 *
 * @property id The notice
 * @property body The text
 * @property postedAt When, as the server wrote it
 * @property edited Whether it has been changed since posting
 */
data class Notice(
    val id: String,
    val body: String,
    val postedAt: String,
    val edited: Boolean,
)

/**
 * Everything the batch screen holds beyond the roster, classes and exams.
 *
 * @property tab The open tab
 * @property header The batch summary, or null until read
 * @property fees The fee chips
 * @property notices The notices, or null until read or when the read failed
 * @property noticeWrite A notice being posted, changed or removed
 * @property batchWrite An edit to the batch itself
 */
data class BatchDetailState(
    val tab: BatchTab = BatchTab.STUDENTS,
    val header: BatchHeader? = null,
    val fees: FeeChips = FeeChips.Loading,
    val notices: List<Notice>? = null,
    val noticeWrite: WriteState = WriteState.Idle,
    val batchWrite: WriteState = WriteState.Idle,
)
