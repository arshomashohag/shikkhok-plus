package com.shikkhokplus.app.feature.sessions

import com.shikkhokplus.app.core.network.ErrorEnvelope
import com.shikkhokplus.app.core.network.SessionDto

/**
 * Maps server responses to a [SessionsUiState].
 *
 * **This object is the unit under test**, rather than "the ViewModel".
 * It is pure: no network, no storage, no clock. A decision needing any
 * of those would be a business rule, and business rules are server-side
 * [TC-9, D-31].
 *
 * **No clock here is load-bearing rather than stylistic.** The natural
 * way to decide whether a class is past is to compare its date against
 * today, and that would be the client holding a rule — wrong across a
 * timezone, wrong against a device clock the user can change, and wrong
 * in the way BR3.3's note rules out for decisions. The server sends
 * `status`; this maps it.
 */
object SessionsStateMapper {
    /** The key shown when the device cannot reach the server at all. */
    const val OFFLINE_KEY: String = "error.network.unreachable"

    /** The key shown when a response cannot be parsed. */
    const val UNEXPECTED_KEY: String = "error.unexpected"

    /**
     * String resource keys for the three server-decided statuses
     * [BR1.6].
     *
     * **The mapping is exhaustive and an unknown value is an error**,
     * not a silent default. A server that added a fourth status would
     * otherwise render every such session under whichever label
     * happened to be the fallback, which is worse than showing nothing
     * — and here the fallback could render a cancelled class as one
     * that is going ahead.
     */
    private val STATUS_KEYS: Map<String, String> =
        mapOf(
            "scheduled" to "session.status.scheduled",
            "held" to "session.status.held",
            "cancelled" to "session.status.cancelled",
        )

    /** The server's value for a session a teacher created by hand. */
    private const val ORIGIN_AD_HOC: String = "ad_hoc"

    /** The server's value for a cancelled session. */
    private const val STATUS_CANCELLED: String = "cancelled"

    /**
     * Map a loaded session list.
     *
     * @param batchName Which class this is
     * @param sessions The sessions the server returned, in its order
     * @return The state the screen renders
     */
    fun afterLoad(
        batchName: String,
        sessions: List<SessionDto>,
    ): SessionsUiState {
        if (sessions.isEmpty()) {
            return SessionsUiState.Empty(batchName)
        }

        val rows =
            sessions.map { dto ->
                toRow(dto)
                    ?: return SessionsUiState.Failed(UNEXPECTED_KEY, retryable = false)
            }
        return SessionsUiState.Loaded(batchName, rows)
    }

    /**
     * Convert one session, or null for an unrecognised status.
     *
     * @param dto The session the server returned
     * @return The row, or null when a value was not recognised
     */
    fun toRow(dto: SessionDto): SessionRow? {
        val label = STATUS_KEYS[dto.status] ?: return null

        return SessionRow(
            sessionId = dto.sessionId,
            dateLabel = dto.date,
            timeLabel = dto.startTime,
            subjectName = dto.subjectName,
            statusLabel = label,
            // Decided here so no composable writes
            // `status == "cancelled"` to choose a mark.
            isCancelled = dto.status == STATUS_CANCELLED,
            isAdHoc = dto.origin == ORIGIN_AD_HOC,
            // **READ, not derived from `topic == null`** [BR2.2]. The
            // derivation would make a deliberately blank topic
            // indistinguishable from one never written, which is the
            // exact distinction the rule exists to preserve.
            topicLogged = dto.topicLogged,
            topic = dto.topic,
            attendanceVersion = dto.attendanceVersion,
            topicVersion = dto.topicVersion,
        )
    }

    /**
     * Map a server error envelope.
     *
     * `retryable` is **read from the envelope**, never inferred from a
     * status code: the client holds no business logic, so it is told
     * rather than deciding [TC-9].
     *
     * @param envelope The server's error
     * @return The state the screen renders
     */
    fun afterError(envelope: ErrorEnvelope): SessionsUiState =
        SessionsUiState.Failed(
            messageKey = envelope.error.messageKey,
            retryable = envelope.error.retryable,
        )

    /**
     * Map a transport failure, where no envelope was received.
     *
     * Always retryable: a read that could not reach the server can be
     * read again. **Reads are not queued** — only the two mid-class
     * write paths queue [BR3.1], and a queued read would be a cache
     * this unit does not build.
     *
     * @return The offline state
     */
    fun afterTransportFailure(): SessionsUiState =
        SessionsUiState.Failed(OFFLINE_KEY, retryable = true)
}
