package com.shikkhokplus.app.feature.classcalendar

import com.shikkhokplus.app.core.network.ErrorBody
import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.SessionDetailDto
import com.shikkhokplus.app.core.network.SessionDto
import com.shikkhokplus.app.core.network.SubjectOptionDto
import com.shikkhokplus.app.core.queue.QueuedWrite
import com.shikkhokplus.app.core.queue.SendOutcome
import com.shikkhokplus.app.core.ui.CalendarClassUi
import com.shikkhokplus.app.core.ui.CalendarState
import com.shikkhokplus.app.feature.auth.AuthResult
import com.shikkhokplus.app.feature.record.RecordRepository
import com.shikkhokplus.app.feature.sessions.SessionsRepository

fun calendarClass(
    id: String = "s-1",
    date: String = "2026-11-16",
    start: String = "16:00:00",
    state: CalendarState = CalendarState.UPCOMING,
    topic: String? = null,
    notes: String? = null,
    plannable: Boolean = false,
    recordable: Boolean = false,
    subject: String? = "Physics",
    topicVersion: Int = 0,
): CalendarClassUi =
    CalendarClassUi(
        id, date, start, null, subject, state, topic, notes, plannable, recordable, null,
        topicVersion = topicVersion,
    )

fun envelope(key: String, code: String = "X"): ErrorEnvelope =
    ErrorEnvelope(ErrorBody(code = code, retryable = false, messageKey = key))

class FakeSessions(private val topicVersion: Int = 5) : SessionsRepository {
    override suspend fun sessions(batchId: String) = AuthResult.Ok(emptyList<SessionDto>())

    override suspend fun sessionDetail(sessionId: String) =
        AuthResult.Ok(
            SessionDetailDto(
                SessionDto(
                    sessionId = sessionId,
                    date = "2026-11-16",
                    startTime = "16:00:00",
                    origin = "recurrence",
                    status = "scheduled",
                    topicVersion = topicVersion,
                    attendanceVersion = 2,
                ),
            ),
        )

    override suspend fun createAdHoc(batchId: String, date: String, startTime: String, batchSubjectId: String?) =
        AuthResult.Ok(Unit)

    override suspend fun reschedule(sessionId: String, date: String, startTime: String) = AuthResult.Ok(Unit)

    override suspend fun cancel(sessionId: String) = AuthResult.Ok(Unit)
}

class FakeTopicSender(
    val outcomes: MutableList<SendOutcome> = mutableListOf(),
    private val options: List<SubjectOptionDto> = emptyList(),
    private val subjectAnswer: AuthResult<Unit> = AuthResult.Ok(Unit),
) : RecordRepository {
    val sent = mutableListOf<QueuedWrite>()
    val subjectWrites = mutableListOf<Pair<String, String?>>()

    override suspend fun subjects(batchId: String) = AuthResult.Ok(options)

    override suspend fun sessions(batchId: String) = AuthResult.Ok(emptyList<SessionDto>())

    override suspend fun setSubject(sessionId: String, batchSubjectId: String?): AuthResult<Unit> {
        subjectWrites += sessionId to batchSubjectId
        return subjectAnswer
    }

    override suspend fun send(item: QueuedWrite): SendOutcome {
        sent += item
        return outcomes.removeFirstOrNull() ?: SendOutcome.Applied(item.baseVersion + 1)
    }
}
