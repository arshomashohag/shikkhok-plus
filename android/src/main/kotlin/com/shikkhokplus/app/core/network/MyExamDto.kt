package com.shikkhokplus.app.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One exam a centre asked me to mark, from `GET /v1/me/exams`.
 *
 * @property examId The exam
 * @property centreName The centre it belongs to
 * @property batchName Its batch's name
 * @property subjectName Its subject
 * @property title The exam's name
 * @property date The day, `yyyy-MM-dd`
 * @property totalMarks What it is out of
 * @property published Whether the results are out
 * @property cancelled Whether it was called off
 */
@Serializable
data class MyExamDto(
    @SerialName("exam_id") val examId: String,
    @SerialName("centre_name") val centreName: String,
    @SerialName("batch_name") val batchName: String,
    @SerialName("subject_name") val subjectName: String,
    @SerialName("title") val title: String,
    @SerialName("date") val date: String,
    @SerialName("total_marks") val totalMarks: Int,
    @SerialName("published") val published: Boolean = false,
    @SerialName("cancelled") val cancelled: Boolean = false,
)

/**
 * One exam's results as its examiner sees them: names and results only.
 *
 * @property exam The exam
 * @property results One row per seat, in the server's order
 * @property writable Whether marks may be written, decided by the server
 */
@Serializable
data class ExaminerResultsDto(
    @SerialName("exam") val exam: MyExamDto,
    @SerialName("results") val results: List<ExamResultDto> = emptyList(),
    @SerialName("writable") val writable: Boolean,
)

/**
 * Who marks one exam, from `GET /v1/exams/{id}` or its examiner write.
 *
 * @property examId The exam
 * @property cancelled Whether it was called off; its examiner cannot change then
 * @property examinerMemberId The examiner, or null for nobody
 * @property examinerName Their name, or null
 */
@Serializable
data class ExamExaminerDto(
    @SerialName("exam_id") val examId: String,
    @SerialName("cancelled") val cancelled: Boolean = false,
    @SerialName("examiner_member_id") val examinerMemberId: String? = null,
    @SerialName("examiner_name") val examinerName: String? = null,
)
